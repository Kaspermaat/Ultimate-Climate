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
from .algorithms.cover import CoverPosition
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
    CONF_WINDOW_TEMP_MAX,
    CONF_WINDOW_TEMP_MIN,
    COVER_HYSTERESIS,
    COVER_TYPE_WINDOW,
    DEFAULT_FOV,
    DEFAULT_ILLUMINANCE_THRESHOLD,
    DEFAULT_MIN_POSITION_CURTAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WINDOW_TEMP_MAX,
    DEFAULT_WINDOW_TEMP_MIN,
    DOMAIN,
    FAN_MIN_SPEED,
    FAN_SUMMER_COOLING_DELTA,
    HUMIDITY_OUTDOOR_MARGIN,
    MODE_AUTO,
    MODE_AWAY,
    MODE_SLEEP,
)

_LOGGER = logging.getLogger(__name__)

_FAN_HYSTERESIS = 5
_COVER_AWAY_POSITION = 10
_COVER_SLEEP_POSITION = 0


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
        self._last_fan_speed: int = -1
        self._last_cover_positions: dict[str, int] = {}
        self._mode: str = MODE_AUTO

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        valid = {MODE_AUTO, MODE_AWAY, MODE_SLEEP, "handmatig"}
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

    def _collect_states(self) -> SensorStates:
        # Gather data from all configured climate entities
        climate_temps: list[float] = []
        temp_setpoints: list[float] = []
        hvac_action: str | None = None

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
                climate_type = cfg.get(CC_CLIMATE_TYPE, "verwarming")
                # For cooling entities, flip the setpoint perspective for comfort scoring
                if climate_type == CLIMATE_TYPE_COOLING:
                    temp_setpoints.append(sp)
                else:
                    temp_setpoints.append(sp)
            if hvac_action is None:
                hvac_action = attrs.get("hvac_action")

        climate_temp = sum(climate_temps) / len(climate_temps) if climate_temps else None
        temp_setpoint = sum(temp_setpoints) / len(temp_setpoints) if temp_setpoints else None

        sun_state = self.hass.states.get("sun.sun")
        sun_azimuth: float | None = None
        sun_elevation: float | None = None
        if sun_state and sun_state.state != "unavailable":
            sun_azimuth = _safe_float(sun_state.attributes.get("azimuth"))
            sun_elevation = _safe_float(sun_state.attributes.get("elevation"))

        return SensorStates(
            co2=self._float_state(self._config.get(CONF_CO2_SENSOR)),
            humidity_indoor=self._float_state(self._config.get(CONF_HUMIDITY_INDOOR)),
            humidity_outdoor=self._float_state(self._config.get(CONF_HUMIDITY_OUTDOOR)),
            temp_indoor=self._average_temp_indoor(climate_temp),
            temp_outdoor=self._float_state(self._config.get(CONF_TEMP_OUTDOOR)),
            temp_setpoint=temp_setpoint,
            climate_hvac_action=hvac_action,
            sun_azimuth=sun_azimuth,
            sun_elevation=sun_elevation,
        )

    def _update_co2_history(self, co2: float | None) -> None:
        if co2 is None:
            return
        self._co2_history.append(co2)
        if len(self._co2_history) > 10:
            self._co2_history.pop(0)

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
            # Windows follow ventilation, not sun angle
            target = 100 if self._mode == MODE_AUTO else 0
            result_reason = "ventilatie"
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

        # For windows: check outdoor temp gate
        if cover_type == COVER_TYPE_WINDOW and target > 0:
            if not self._window_temp_allowed(states):
                target = 0
                result_reason = "temperatuur_buiten_bereik"

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
    # Temperature gate for windows
    # ------------------------------------------------------------------

    def _window_temp_allowed(self, states: SensorStates) -> bool:
        if states.temp_outdoor is None:
            return True
        temp_min = float(self._config.get(CONF_WINDOW_TEMP_MIN, DEFAULT_WINDOW_TEMP_MIN))
        temp_max = float(self._config.get(CONF_WINDOW_TEMP_MAX, DEFAULT_WINDOW_TEMP_MAX))
        if temp_min <= states.temp_outdoor <= temp_max:
            return True
        co2_critical = states.co2 is not None and states.co2 > CO2_POOR
        if co2_critical:
            _LOGGER.debug(
                "Raam openen ondanks buitentemp %.1f°C — CO₂ kritiek", states.temp_outdoor
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Mode-aware action dispatch
    # ------------------------------------------------------------------

    async def _async_apply_actions(
        self, fan: FanAdvice, states: SensorStates, season: Season
    ) -> list[CoverResult]:
        cover_cfgs = self._cover_config_list()
        results: list[CoverResult] = []

        if self.mode == MODE_AWAY:
            await self._async_apply_fan(FAN_MIN_SPEED)
            for cfg in cover_cfgs:
                cover_type = cfg.get(CC_TYPE, "shutter")
                pos = 0 if cover_type == COVER_TYPE_WINDOW else _COVER_AWAY_POSITION
                results.append(await self._async_apply_one_cover(cfg, states, season, forced_position=pos))
            return results

        if self.mode == MODE_SLEEP:
            await self._async_apply_fan(min(fan.speed_pct, 50))
            for cfg in cover_cfgs:
                results.append(
                    await self._async_apply_one_cover(cfg, states, season, forced_position=_COVER_SLEEP_POSITION)
                )
            return results

        if self.mode != MODE_AUTO:
            # Manual — no writes, return empty
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
        )
