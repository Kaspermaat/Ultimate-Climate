"""Coordinator: collects sensor states, runs algorithms, and drives actuators."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .algorithms import comfort as comfort_algo
from .algorithms import fan as fan_algo
from .algorithms import ventilation as ventilation_algo
from .algorithms import cover as cover_algo
from .algorithms.comfort import ComfortScore
from .algorithms.cover import CoverPosition, CoverReason
from .algorithms.fan import FanAdvice, Season, detect_season
from .algorithms.ventilation import VentilationAdvice
from .const import (
    CC_AZIMUTH,
    CC_CLIMATE_ENTITY,
    CC_CLIMATE_TYPE,
    CC_CURTAIN_MIN_OPEN,
    CC_ENTITY_ID,
    CC_FOV,
    CC_ILLUMINANCE_SENSOR,
    CC_ILLUMINANCE_THRESHOLD,
    CC_LINKED_CURTAIN,
    CC_MIN_POSITION,
    CC_SUN_PROTECTION,
    CC_TEMP_SENSOR,
    CC_TYPE,
    CLIMATE_TYPE_COOLING,
    CLIMATE_TYPE_HEATING,
    CLOUD_COVERAGE_NO_SUN,
    CO2_GOOD,
    CO2_MODERATE,
    CO2_POOR,
    CONF_CLIMATE_CONFIGS,
    CONF_CLIMATE_ENTITY,
    CONF_CO2_SENSOR,
    CONF_COVER_CONFIGS,
    CONF_FAN_ENTITY,
    CONF_HUMIDITY_INDOOR,
    CONF_HUMIDITY_OUTDOOR,
    CONF_TEMP_OUTDOOR,
    CONF_TEMP_SENSORS,
    CONF_IDEAL_TEMP,
    CONF_WINDOW_TEMP_MAX,
    CONF_WINDOW_TEMP_MIN,
    CONF_WINDOW_AWAY_POSITION,
    CONF_WINDOW_RAIN_POSITION,
    CONF_WINDOW_SLEEP_POSITION,
    COVER_HYSTERESIS,
    COVER_TYPE_CURTAIN,
    COVER_TYPE_WINDOW,
    DEFAULT_FOV,
    DEFAULT_ILLUMINANCE_THRESHOLD,
    DEFAULT_MIN_POSITION_CURTAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WINDOW_AWAY_POSITION,
    DEFAULT_WINDOW_RAIN_POSITION,
    DEFAULT_WINDOW_SLEEP_POSITION,
    DEFAULT_IDEAL_TEMP,
    DEFAULT_WINDOW_TEMP_MAX,
    DEFAULT_WINDOW_TEMP_MIN,
    DOMAIN,
    FAN_MIN_SPEED,
    FAN_SUMMER_COOLING_DELTA,
    HUMIDITY_OUTDOOR_MARGIN,
    MODE_AUTO,
    MODE_AWAY,
    MODE_SLEEP,
    WEATHER_ENTITY_CANDIDATES,
    WEATHER_RAIN_CONDITIONS,
    WEATHER_WIND_CONDITIONS,
    WIND_SPEED_MAX_WINDOW,
)

_LOGGER = logging.getLogger(__name__)

_FAN_HYSTERESIS = 5
_COVER_AWAY_POSITION = 10
_COVER_SLEEP_POSITION = 0
_NATURAL_COOLING_DELTA = 2.0   # buiten moet minstens 2°C koeler zijn dan binnen


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class SensorStates:
    co2: float | None = None
    humidity_indoor: float | None = None
    humidity_outdoor: float | None = None
    temp_indoor: float | None = None        # averaged across all zone temp sensors
    temp_outdoor: float | None = None
    temp_setpoint: float | None = None
    climate_hvac_action: str | None = None
    sun_azimuth: float | None = None
    sun_elevation: float | None = None
    ac_actively_cooling: bool = False       # any cooling entity has hvac_action=cooling
    heating_active: bool = False            # any heating entity has hvac_action=heating
    natural_cooling_possible: bool = False  # buiten koeler dan binnen met voldoende marge
    ideal_temp: float | None = None         # centrale doeltemperatuur (config > thermostaat-setpoint)
    # Weather (auto-detected via Buienradar / weather.home)
    weather_entity: str | None = None
    weather_condition: str | None = None   # e.g. "rainy", "sunny", "cloudy"
    wind_speed: float | None = None        # km/h
    cloud_coverage: int | None = None      # 0-100 %
    rain_active: bool = False              # regen of storm nu actief
    wind_too_strong: bool = False          # wind boven drempel voor ramen
    heavily_overcast: bool = False         # bewolking > drempel → geen zonwering nodig


@dataclass
class CoverResult:
    entity_id: str
    position: int
    reason: str
    label: str


@dataclass
class ClimateSnapshot:
    sensors: SensorStates
    comfort: ComfortScore
    ventilation: VentilationAdvice
    fan: FanAdvice
    covers: list[CoverResult]
    mode: str
    co2_history: list[float] = field(default_factory=list)
    temp_history: list[float] = field(default_factory=list)

    @property
    def co2_trend(self) -> str:
        if len(self.co2_history) < 2:
            return "onbekend"
        delta = self.co2_history[-1] - self.co2_history[-2]
        if delta > 30:
            return "stijgend"
        if delta < -30:
            return "dalend"
        return "stabiel"


class OptimalClimateCoordinator(DataUpdateCoordinator[ClimateSnapshot]):
    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._entry = config_entry
        self._co2_history: list[float] = []
        self._temp_history: list[float] = []   # binnentemp per poll-cyclus (max 10)
        self._last_fan_speed: int = -1
        self._last_cover_positions: dict[str, int] = {}
        self._mode: str = MODE_AUTO
        self._ideal_temp: float = float(
            config_entry.options.get(CONF_IDEAL_TEMP)
            or config_entry.data.get(CONF_IDEAL_TEMP)
            or DEFAULT_IDEAL_TEMP
        )

    @property
    def ideal_temp(self) -> float:
        return self._ideal_temp

    @ideal_temp.setter
    def ideal_temp(self, value: float) -> None:
        self._ideal_temp = float(value)

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        valid = {MODE_AUTO, MODE_AWAY, MODE_SLEEP, "handmatig", "uit"}
        if value not in valid:
            _LOGGER.warning("Ongeldige modus '%s' genegeerd", value)
            return
        self._mode = value

    @property
    def _config(self) -> dict:
        """Merged config: options override original data."""
        return {**self._entry.data, **self._entry.options}

    # ------------------------------------------------------------------
    # Sensor state collection
    # ------------------------------------------------------------------

    def _float_state(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown", ""):
            return None
        return _safe_float(state.state)

    def _climate_config_list(self) -> list[dict]:
        """Return list of climate configs, with legacy single-entity migration."""
        cfgs = list(self._config.get(CONF_CLIMATE_CONFIGS) or [])
        # Migrate old single-entity config
        if not cfgs and self._config.get(CONF_CLIMATE_ENTITY):
            cfgs = [{CC_CLIMATE_ENTITY: self._config[CONF_CLIMATE_ENTITY], CC_CLIMATE_TYPE: "verwarming"}]
        return cfgs

    def _average_temp_indoor(self, climate_temp: float | None) -> float | None:
        """Average all configured indoor temperature sensors + climate entities."""
        values: list[float] = []
        if climate_temp is not None:
            values.append(climate_temp)
        for sensor_id in self._config.get(CONF_TEMP_SENSORS) or []:
            val = self._float_state(sensor_id)
            if val is not None:
                values.append(val)
        if not values:
            return None
        return sum(values) / len(values)

    def _get_weather_entity(self) -> str | None:
        """Auto-detect weather entity: Buienradar first, then common fallbacks."""
        for candidate in WEATHER_ENTITY_CANDIDATES:
            if self.hass.states.get(candidate) is not None:
                return candidate
        return None

    def _collect_weather(self) -> dict:
        """Read weather state from auto-detected entity. Returns empty dict if unavailable."""
        weather_eid = self._get_weather_entity()
        if not weather_eid:
            return {}
        ws = self.hass.states.get(weather_eid)
        if not ws or ws.state in ("unavailable", "unknown"):
            return {}

        condition = ws.state
        wind_speed_val = _safe_float(ws.attributes.get("wind_speed"))
        cc_raw = ws.attributes.get("cloud_coverage")
        cloud_coverage_val = int(cc_raw) if cc_raw is not None else None

        rain_active = condition in WEATHER_RAIN_CONDITIONS
        wind_too_strong = (
            condition in WEATHER_WIND_CONDITIONS
            or (wind_speed_val is not None and wind_speed_val >= WIND_SPEED_MAX_WINDOW)
        )
        heavily_overcast = (
            cloud_coverage_val is not None and cloud_coverage_val >= CLOUD_COVERAGE_NO_SUN
        )

        _LOGGER.debug(
            "Weer via %s: conditie=%s wind=%.0f km/h bewolking=%s%% "
            "regen=%s wind_te_hard=%s zwaar_bewolkt=%s",
            weather_eid, condition,
            wind_speed_val or 0,
            cloud_coverage_val if cloud_coverage_val is not None else "?",
            rain_active, wind_too_strong, heavily_overcast,
        )

        return {
            "weather_entity": weather_eid,
            "weather_condition": condition,
            "wind_speed": wind_speed_val,
            "cloud_coverage": cloud_coverage_val,
            "rain_active": rain_active,
            "wind_too_strong": wind_too_strong,
            "heavily_overcast": heavily_overcast,
        }

    def _collect_states(self) -> SensorStates:
        # Gather data from all configured climate entities
        climate_temps: list[float] = []
        temp_setpoints: list[float] = []
        hvac_action: str | None = None
        ac_actively_cooling = False
        heating_active = False

        for cfg in self._climate_config_list():
            entity_id = cfg.get(CC_CLIMATE_ENTITY)
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if not state or state.state in ("unavailable", "unknown"):
                continue
            attrs = state.attributes
            t = _safe_float(attrs.get("current_temperature"))
            if t is not None:
                climate_temps.append(t)
            sp = _safe_float(attrs.get("temperature"))
            if sp is not None:
                temp_setpoints.append(sp)
            action = attrs.get("hvac_action")
            if hvac_action is None:
                hvac_action = action
            # Actieve koeling detecteren
            if cfg.get(CC_CLIMATE_TYPE) == CLIMATE_TYPE_COOLING and action == "cooling":
                ac_actively_cooling = True
            # Actieve verwarming detecteren
            if cfg.get(CC_CLIMATE_TYPE) == CLIMATE_TYPE_HEATING and action == "heating":
                heating_active = True

        climate_temp = sum(climate_temps) / len(climate_temps) if climate_temps else None
        temp_setpoint = sum(temp_setpoints) / len(temp_setpoints) if temp_setpoints else None

        temp_indoor_avg = self._average_temp_indoor(climate_temp)
        temp_outdoor_val = self._float_state(self._config.get(CONF_TEMP_OUTDOOR))
        natural_cooling = (
            temp_indoor_avg is not None
            and temp_outdoor_val is not None
            and temp_indoor_avg - temp_outdoor_val >= _NATURAL_COOLING_DELTA
        )

        sun_state = self.hass.states.get("sun.sun")
        sun_azimuth: float | None = None
        sun_elevation: float | None = None
        if sun_state and sun_state.state != "unavailable":
            sun_azimuth = _safe_float(sun_state.attributes.get("azimuth"))
            sun_elevation = _safe_float(sun_state.attributes.get("elevation"))

        weather = self._collect_weather()

        # Centrale doeltemperatuur: thermostaat-entiteit wint van thermostaat-setpoint
        ideal_temp = self._ideal_temp if self._ideal_temp is not None else temp_setpoint

        return SensorStates(
            co2=self._float_state(self._config.get(CONF_CO2_SENSOR)),
            humidity_indoor=self._float_state(self._config.get(CONF_HUMIDITY_INDOOR)),
            humidity_outdoor=self._float_state(self._config.get(CONF_HUMIDITY_OUTDOOR)),
            temp_indoor=temp_indoor_avg,
            temp_outdoor=temp_outdoor_val,
            temp_setpoint=temp_setpoint,
            climate_hvac_action=hvac_action,
            sun_azimuth=sun_azimuth,
            sun_elevation=sun_elevation,
            ac_actively_cooling=ac_actively_cooling,
            heating_active=heating_active,
            natural_cooling_possible=natural_cooling,
            ideal_temp=ideal_temp,
            **weather,
        )

    def _update_co2_history(self, co2: float | None) -> None:
        if co2 is None:
            return
        self._co2_history.append(co2)
        if len(self._co2_history) > 10:
            self._co2_history.pop(0)

    def _update_temp_history(self, temp: float | None) -> None:
        if temp is None:
            return
        self._temp_history.append(temp)
        if len(self._temp_history) > 10:
            self._temp_history.pop(0)

    def _temp_trend_toward_setpoint(self, setpoint: float, want_cooling: bool) -> bool:
        """Return True als de binnentemp de laatste cycli richting setpoint beweegt."""
        if len(self._temp_history) < 3:
            return True  # te weinig data → aannemen dat het werkt
        recent = self._temp_history[-3:]
        delta = recent[-1] - recent[0]   # positief = stijgend
        if want_cooling:
            return delta < -0.1           # temp moet dalen
        return delta > 0.1               # temp moet stijgen

    def _calculate_window_position(self, states: SensorStates) -> int:
        """Bereken proportionele raam-opening op basis van temp-afwijking van setpoint.

        Koeling gewenst (binnen > setpoint):
          - Schaalt van 20% (bij 0.5°C overschot) tot 100% (bij 4°C+ overschot)
          - +15% als de temp na 3 cycli (~90s) nog niet daalt (feedback-boost)

        Opwarming via buitenlucht (binnen < setpoint en buiten > indoor):
          - Vaste 20% — zachte toevoer
          - Geen boost want verwarmen via raam is al een noodgeval

        Neutrale ventilatie (geen noemenswaardige afwijking):
          - 100% open voor maximale luchtkwaliteit
        """
        indoor = states.temp_indoor
        outdoor = states.temp_outdoor
        target = states.temp_setpoint if states.temp_setpoint is not None else indoor

        # Ideale temp als referentie (config > thermostaat-setpoint > binnentemp)
        target = states.ideal_temp if states.ideal_temp is not None else indoor

        if indoor is None or target is None:
            return 100

        excess = indoor - target   # positief = te warm, negatief = te koud

        if excess > 0.5:
            # Koeling via ventilatie: proportioneel openen
            # 0.5°C → 20%, 4°C+ → 100%  (lineair over 3.5°C bereik)
            base = min(100, max(20, int(20 + (excess - 0.5) / 3.5 * 80)))
            improving = self._temp_trend_toward_setpoint(target, want_cooling=True)
            if not improving:
                base = min(100, base + 15)
                _LOGGER.debug(
                    "Raam-boost: temp %.1f°C daalt niet richting setpoint %.1f°C → +15%%",
                    indoor, target,
                )
            _LOGGER.debug(
                "Raam proportioneel: excess=%.1f°C → positie=%d%% (boost=%s)",
                excess, base, not improving,
            )
            return base

        if excess < -0.5 and outdoor is not None and outdoor > indoor:
            # Binnen te koud maar buitenlucht is warmer → voorzichtig openen
            _LOGGER.debug(
                "Raam 20%% voor opwarming: binnen %.1f°C < setpoint %.1f°C, buiten %.1f°C warmer",
                indoor, target, outdoor,
            )
            return 20

        # Binnen op setpoint: volledig open voor luchtverversing
        return 100

    # ------------------------------------------------------------------
    # Fan actuator
    # ------------------------------------------------------------------

    async def _async_apply_fan(self, speed_pct: int) -> None:
        entity_id: str | None = self._config.get(CONF_FAN_ENTITY)
        if not entity_id:
            return
        if abs(speed_pct - self._last_fan_speed) < _FAN_HYSTERESIS:
            return

        domain = entity_id.split(".")[0]
        try:
            if domain == "fan":
                await self._async_apply_fan_entity(entity_id, speed_pct)
            elif domain == "number":
                await self._async_apply_number_entity(entity_id, speed_pct)
            else:
                _LOGGER.warning("Onbekend fan domain '%s' voor %s", domain, entity_id)
                return
        except Exception as exc:
            _LOGGER.error("Fout bij aansturen afzuiging %s: %s", entity_id, exc)
            return

        _LOGGER.debug("Afzuiging %s → %d%% (was %d%%)", entity_id, speed_pct, self._last_fan_speed)
        self._last_fan_speed = speed_pct

    async def _async_apply_fan_entity(self, entity_id: str, speed_pct: int) -> None:
        if speed_pct == 0:
            await self.hass.services.async_call(
                "fan", "turn_off", {"entity_id": entity_id}, blocking=True
            )
            return
        state = self.hass.states.get(entity_id)
        if state and state.state == "off":
            await self.hass.services.async_call(
                "fan", "turn_on", {"entity_id": entity_id}, blocking=True
            )
        await self.hass.services.async_call(
            "fan", "set_percentage",
            {"entity_id": entity_id, "percentage": speed_pct},
            blocking=True,
        )

    async def _async_apply_number_entity(self, entity_id: str, speed_pct: int) -> None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.warning("Fan number entity %s niet beschikbaar", entity_id)
            return
        attrs = state.attributes
        min_val = float(attrs.get("min", 0))
        max_val = float(attrs.get("max", 100))
        step = max(float(attrs.get("step", 1)), 0.001)  # guard against step=0
        raw = min_val + (speed_pct / 100) * (max_val - min_val)
        value = max(min_val, min(max_val, round(round(raw / step) * step, 10)))
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    # ------------------------------------------------------------------
    # Cover actuator (single cover)
    # ------------------------------------------------------------------

    async def _async_set_cover_position(self, entity_id: str, position: int) -> None:
        last = self._last_cover_positions.get(entity_id, -1)
        if abs(position - last) < COVER_HYSTERESIS:
            return
        try:
            await self.hass.services.async_call(
                "cover", "set_cover_position",
                {"entity_id": entity_id, "position": position},
                blocking=True,
            )
            _LOGGER.debug("Cover %s → %d%% (was %d%%)", entity_id, position, last)
            self._last_cover_positions[entity_id] = position
        except Exception as exc:
            _LOGGER.error("Fout bij aansturen cover %s: %s", entity_id, exc)

    # ------------------------------------------------------------------
    # Curtain dependency
    # ------------------------------------------------------------------

    async def _async_ensure_curtain_open(
        self, curtain_id: str, min_open: int, context_window: str
    ) -> bool:
        """Ensure curtain is at least min_open % open before window opens.

        Returns False if curtain is fully closed and couldn't be moved.
        """
        curtain_state = self.hass.states.get(curtain_id)
        if curtain_state is None or curtain_state.state in ("unavailable", "unknown"):
            return True  # unknown — allow window to proceed

        curtain_pos = _safe_float(curtain_state.attributes.get("current_position"))
        if curtain_pos is None:
            return True

        if curtain_pos < 5:
            _LOGGER.debug(
                "Raam %s geblokkeerd: gordijn %s volledig dicht (%.0f%%)",
                context_window, curtain_id, curtain_pos,
            )
            return False  # don't open window — curtain would be damaged

        if curtain_pos < min_open:
            try:
                await self.hass.services.async_call(
                    "cover", "set_cover_position",
                    {"entity_id": curtain_id, "position": min_open},
                    blocking=True,
                )
                _LOGGER.debug(
                    "Gordijn %s → %d%% voor ventilatie via raam %s",
                    curtain_id, min_open, context_window,
                )
            except Exception as exc:
                _LOGGER.error("Gordijn %s aansturen mislukt: %s", curtain_id, exc)
                return False

        return True

    # ------------------------------------------------------------------
    # Per-cover algorithm + apply
    # ------------------------------------------------------------------

    def _cover_config_list(self) -> list[dict]:
        return list(self._config.get(CONF_COVER_CONFIGS) or [])

    async def _async_apply_one_cover(
        self,
        cfg: dict,
        states: SensorStates,
        season: Season,
        forced_position: int | None = None,
    ) -> CoverResult:
        """Calculate and apply the position for a single cover config.

        forced_position: set by away/sleep mode, bypasses algorithm.
        """
        entity_id: str = cfg[CC_ENTITY_ID]
        azimuth = float(cfg.get(CC_AZIMUTH, 180))
        fov = float(cfg.get(CC_FOV, DEFAULT_FOV))
        min_pos = int(cfg.get(CC_MIN_POSITION, DEFAULT_MIN_POSITION_CURTAIN))
        cover_type: str = cfg.get(CC_TYPE, "shutter")
        sun_protection: bool = cfg.get(CC_SUN_PROTECTION, True)
        linked_curtain: str | None = cfg.get(CC_LINKED_CURTAIN)
        curtain_min_open = int(cfg.get(CC_CURTAIN_MIN_OPEN, 10))

        # Illuminance for this specific cover
        illuminance = self._float_state(cfg.get(CC_ILLUMINANCE_SENSOR))
        illuminance_threshold = float(
            cfg.get(CC_ILLUMINANCE_THRESHOLD, DEFAULT_ILLUMINANCE_THRESHOLD)
        )

        if forced_position is not None:
            target = forced_position
            result_reason = "geforceerd"
        elif not sun_protection:
            target = 100
            result_reason = "zonwering_uit"
        elif cover_type == COVER_TYPE_WINDOW:
            # Ramen: proportioneel op basis van temp-afwijking van setpoint
            target = self._calculate_window_position(states) if self._mode == MODE_AUTO else 0
            result_reason = "ventilatie"
        elif states.heavily_overcast:
            # Zware bewolking → normaal geen zonwering nodig.
            # Maar als de lux-sensor aangeeft dat de zon toch doorkomt én binnen
            # de ideale temp nadert, zet wel zonwering in als warmtewering.
            lux_high = illuminance is not None and illuminance >= illuminance_threshold
            indoor = states.temp_indoor
            ideal = states.ideal_temp
            temp_warm_enough = (
                indoor is not None
                and ideal is not None
                and indoor >= ideal - 1.0   # binnen ≤ 1°C onder doel: zon mag niet verder opwarmen
            )
            lux_override = lux_high and temp_warm_enough
            if lux_override:
                _LOGGER.debug(
                    "Cover %s: bewolkt maar lux %.0f lx ≥ drempel en binnen %.1f°C ≥ (doel %.1f°C - 1) "
                    "→ zonwering actief als warmtewering",
                    entity_id, illuminance, indoor, ideal,
                )
                pos = cover_algo.calculate(
                    sun_azimuth=states.sun_azimuth or 0.0,
                    sun_elevation=states.sun_elevation or -1.0,
                    window_azimuth=azimuth,
                    season=season,
                    window_fov=fov,
                    min_position=min_pos,
                    illuminance=illuminance,
                    illuminance_threshold=illuminance_threshold,
                )
                target = pos.position
                result_reason = pos.reason
            elif lux_high:
                # Lux hoog maar binnen nog koel genoeg → zon binnenlaten, geen zonwering
                _LOGGER.debug(
                    "Cover %s: bewolkt + lux hoog maar binnen %.1f°C ruim onder doel %.1f°C "
                    "→ zon binnenlaten",
                    entity_id, indoor if indoor is not None else 0.0, ideal if ideal is not None else 0.0,
                )
                target = 100
                result_reason = "bewolkt"
            else:
                target = 100
                result_reason = "bewolkt"
        else:
            pos = cover_algo.calculate(
                sun_azimuth=states.sun_azimuth or 0.0,
                sun_elevation=states.sun_elevation or -1.0,
                window_azimuth=azimuth,
                season=season,
                window_fov=fov,
                min_position=min_pos,
                illuminance=illuminance,
                illuminance_threshold=illuminance_threshold,
            )
            target = pos.position
            result_reason = pos.reason

            # Gordijnen gaan 's nachts dicht (shutters blijven open)
            if cover_type == COVER_TYPE_CURTAIN and result_reason == CoverReason.SUN_BELOW_HORIZON:
                target = 0
                result_reason = "nacht_gordijn_dicht"

        # For windows: regen/wind sluiten altijd, daarna temp/airco-logica
        if cover_type == COVER_TYPE_WINDOW and target > 0:
            rain_pos = int(self._config.get(CONF_WINDOW_RAIN_POSITION, DEFAULT_WINDOW_RAIN_POSITION))
            if states.rain_active:
                target = rain_pos
                result_reason = "regen"
                _LOGGER.debug(
                    "Raam %s → %d%%: regen (%s)", entity_id, rain_pos, states.weather_condition
                )
            elif states.wind_too_strong:
                target = 0
                result_reason = "harde_wind"
                _LOGGER.debug(
                    "Raam %s dicht: harde wind (%.0f km/h)",
                    entity_id, states.wind_speed or 0,
                )
            elif states.ac_actively_cooling:
                # Airco actief → raam nooit open, anders gaat alle koude lucht verloren
                target = 0
                result_reason = "airco_actief"
                _LOGGER.debug("Raam %s dicht: airco actief", entity_id)
            elif states.heating_active:
                # Thermostaat verwarmt → raam dicht, anders gooi je warmte weg
                target = 0
                result_reason = "verwarming_actief"
                _LOGGER.debug("Raam %s dicht: thermostaat verwarmt", entity_id)
            elif not self._window_temp_allowed(states):
                target = 0
                result_reason = "temperatuur_buiten_bereik"
            elif states.natural_cooling_possible:
                # Buitenlucht ≥ 2°C koeler dan binnen → raam open, airco uit indien aan
                result_reason = "natuurlijke_koeling"
                _LOGGER.info(
                    "Raam %s open voor natuurlijke koeling (buiten %.1f°C, binnen %.1f°C)",
                    entity_id,
                    states.temp_outdoor,
                    states.temp_indoor,
                )
                if states.ac_actively_cooling:
                    await self._async_turn_off_cooling_entities()

        # For windows: handle curtain dependency
        if cover_type == COVER_TYPE_WINDOW and target > 0 and linked_curtain:
            ok = await self._async_ensure_curtain_open(
                linked_curtain, curtain_min_open, entity_id
            )
            if not ok:
                target = 0
                result_reason = "gordijn_dicht"

        await self._async_set_cover_position(entity_id, target)

        return CoverResult(
            entity_id=entity_id,
            position=target,
            reason=result_reason,
            label=str(result_reason),
        )

    # ------------------------------------------------------------------
    # Airco uitschakelen bij natuurlijke koeling
    # ------------------------------------------------------------------

    async def _async_turn_off_cooling_entities(self) -> None:
        """Zet alle actief-koelende airco's uit als natuurlijke ventilatie volstaat."""
        for cfg in self._climate_config_list():
            if cfg.get(CC_CLIMATE_TYPE) != CLIMATE_TYPE_COOLING:
                continue
            entity_id = cfg.get(CC_CLIMATE_ENTITY)
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if not state or state.attributes.get("hvac_action") != "cooling":
                continue
            try:
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": "off"},
                    blocking=True,
                )
                _LOGGER.info(
                    "Airco %s uitgeschakeld — buitenlucht koeler dan binnen, ramen gaan open",
                    entity_id,
                )
            except Exception as exc:
                _LOGGER.error("Airco %s uitschakelen mislukt: %s", entity_id, exc)

    # ------------------------------------------------------------------
    # Temperature gate for windows
    # ------------------------------------------------------------------

    def _window_temp_allowed(self, states: SensorStates) -> bool:
        """Bepaal of de buitentemperatuur het openen van ramen rechtvaardigt.

        Relatief aan de doeltemperatuur (setpoint van thermostaat/airco):
        - Binnen te warm (> setpoint+0.5): open als buiten koeler dan binnen (koeling via ventilatie)
        - Binnen op/onder setpoint: open alleen als buiten >= setpoint (anders verder afkoelen)
        CO2 kritiek overschrijft altijd.
        """
        outdoor = states.temp_outdoor
        indoor = states.temp_indoor

        if outdoor is None:
            return True

        co2_critical = states.co2 is not None and states.co2 > CO2_POOR
        temp_min = float(self._config.get(CONF_WINDOW_TEMP_MIN, DEFAULT_WINDOW_TEMP_MIN))

        # Absolute ondergrens: te koud om te ventileren
        if outdoor < temp_min:
            if co2_critical:
                _LOGGER.debug("Raam toch open ondanks %.1f°C buiten — CO2 kritiek", outdoor)
                return True
            return False

        if indoor is None:
            return True

        # Ideale temp als referentie (config > thermostaat-setpoint > binnentemp)
        target = states.ideal_temp if states.ideal_temp is not None else indoor

        if indoor > target + 0.5:
            # Binnen te warm — koeling gewenst → open als buiten koeler dan binnen
            allowed = outdoor < indoor
            _LOGGER.debug(
                "Raam [te warm]: binnen %.1f > doel %.1f; buiten %.1f → %s",
                indoor, target, outdoor, "open" if allowed else "dicht",
            )
        else:
            # Binnen op/onder setpoint — open alleen als buitenlucht niet verder afkoelt
            allowed = outdoor >= target
            _LOGGER.debug(
                "Raam [stabiel/koud]: binnen %.1f ≤ doel %.1f; buiten %.1f → %s",
                indoor, target, outdoor, "open" if allowed else "dicht",
            )

        if not allowed and co2_critical:
            _LOGGER.debug("Raam toch open — CO2 kritiek (%.0f ppm)", states.co2)
            return True

        return allowed

    # ------------------------------------------------------------------
    # Mode-aware action dispatch
    # ------------------------------------------------------------------

    async def _async_apply_actions(
        self, fan: FanAdvice, states: SensorStates, season: Season
    ) -> list[CoverResult]:
        cover_cfgs = self._cover_config_list()
        results: list[CoverResult] = []

        if self.mode == MODE_AWAY:
            away_window_pos = int(
                self._config.get(CONF_WINDOW_AWAY_POSITION, DEFAULT_WINDOW_AWAY_POSITION)
            )
            # Fan blijft CO₂/vochtigheid respecteren ook bij afwezigheid — gezondheid gaat voor
            away_fan = max(FAN_MIN_SPEED, fan.speed_pct) if fan.reason.value in (
                "co2_kritiek", "co2_verhoogd", "co2_matig", "vochtigheid_hoog"
            ) else FAN_MIN_SPEED
            await self._async_apply_fan(away_fan)
            for cfg in cover_cfgs:
                cover_type = cfg.get(CC_TYPE, "shutter")
                if cover_type == COVER_TYPE_WINDOW:
                    # Raam op geconfigureerde positie (standaard dicht)
                    results.append(
                        await self._async_apply_one_cover(cfg, states, season, forced_position=away_window_pos)
                    )
                else:
                    # Shutters en gordijnen: gewone zonwerings-logica (weren warmte ook bij afwezigheid)
                    results.append(await self._async_apply_one_cover(cfg, states, season))
            return results

        if self.mode == MODE_SLEEP:
            sleep_window_pos = int(
                self._config.get(CONF_WINDOW_SLEEP_POSITION, DEFAULT_WINDOW_SLEEP_POSITION)
            )
            await self._async_apply_fan(min(fan.speed_pct, 50))
            for cfg in cover_cfgs:
                cover_type = cfg.get(CC_TYPE, "shutter")
                if cover_type == COVER_TYPE_WINDOW:
                    results.append(
                        await self._async_apply_one_cover(cfg, states, season, forced_position=sleep_window_pos)
                    )
                else:
                    results.append(await self._async_apply_one_cover(cfg, states, season))
            return results

        if self.mode in ("handmatig", "uit"):
            # Handmatig of uit — geen automatische aansturing
            return []

        await self._async_apply_fan(fan.speed_pct)
        for cfg in cover_cfgs:
            results.append(await self._async_apply_one_cover(cfg, states, season))
        return results

    # ------------------------------------------------------------------
    # DataUpdateCoordinator hook
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> ClimateSnapshot:
        try:
            states = await self.hass.async_add_executor_job(self._collect_states)
        except Exception as exc:
            raise UpdateFailed(f"Fout bij ophalen sensordata: {exc}") from exc

        self._update_co2_history(states.co2)
        self._update_temp_history(states.temp_indoor)
        season = detect_season(states.temp_outdoor)

        comfort = comfort_algo.calculate(
            co2=states.co2,
            humidity_indoor=states.humidity_indoor,
            temp_indoor=states.temp_indoor,
            temp_setpoint=states.temp_setpoint,
        )

        ventilation = ventilation_algo.calculate(
            co2=states.co2,
            humidity_indoor=states.humidity_indoor,
            humidity_outdoor=states.humidity_outdoor,
            co2_good=CO2_GOOD,
            co2_moderate=CO2_MODERATE,
            co2_poor=CO2_POOR,
            humidity_outdoor_margin=HUMIDITY_OUTDOOR_MARGIN,
        )

        fan = fan_algo.calculate(
            co2=states.co2,
            temp_indoor=states.temp_indoor,
            temp_outdoor=states.temp_outdoor,
            humidity_indoor=states.humidity_indoor,
            humidity_outdoor=states.humidity_outdoor,
            co2_good=CO2_GOOD,
            co2_moderate=CO2_MODERATE,
            co2_poor=CO2_POOR,
            summer_cooling_delta=FAN_SUMMER_COOLING_DELTA,
            humidity_outdoor_margin=HUMIDITY_OUTDOOR_MARGIN,
            min_speed=FAN_MIN_SPEED,
            ac_actively_cooling=states.ac_actively_cooling,
            heating_active=states.heating_active,
        )

        cover_results = await self._async_apply_actions(fan, states, season)

        return ClimateSnapshot(
            sensors=states,
            comfort=comfort,
            ventilation=ventilation,
            fan=fan,
            covers=cover_results,
            mode=self.mode,
            co2_history=list(self._co2_history),
            temp_history=list(self._temp_history),
        )
