"""Coordinator: collects sensor states, runs algorithms, and drives actuators."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .algorithms import comfort as comfort_algo
from .algorithms import cover as cover_algo
from .algorithms import fan as fan_algo
from .algorithms import ventilation as ventilation_algo
from .algorithms.comfort import ComfortScore
from .algorithms.cover import CoverPosition
from .algorithms.fan import FanAdvice, Season, detect_season
from .algorithms.ventilation import VentilationAdvice
from .const import (
    CO2_GOOD,
    CO2_MODERATE,
    CO2_POOR,
    CONF_CLIMATE_ENTITY,
    CONF_CO2_SENSOR,
    CONF_COVER_ENTITIES,
    CONF_CURTAIN_MIN_OPEN,
    CONF_FAN_ENTITY,
    CONF_HUMIDITY_INDOOR,
    CONF_HUMIDITY_OUTDOOR,
    CONF_TEMP_OUTDOOR,
    CONF_WINDOW_AZIMUTH,
    CONF_WINDOW_CURTAIN_MAP,
    CONF_WINDOW_ENTITIES,
    CONF_WINDOW_FOV,
    CONF_WINDOW_TEMP_MAX,
    CONF_WINDOW_TEMP_MIN,
    COVER_HYSTERESIS,
    DEFAULT_CURTAIN_MIN_OPEN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WINDOW_AZIMUTH,
    DEFAULT_WINDOW_FOV,
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


def _safe_float(value: object) -> float | None:
    """Convert any value from an entity attribute to float, or None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

# Cover position for away/sleep mode (% open — nearly closed for privacy/safety)
_COVER_AWAY_POSITION = 10
_COVER_SLEEP_POSITION = 0


@dataclass
class SensorStates:
    co2: float | None = None
    humidity_indoor: float | None = None
    humidity_outdoor: float | None = None
    temp_indoor: float | None = None
    temp_outdoor: float | None = None
    temp_setpoint: float | None = None
    climate_hvac_action: str | None = None
    sun_azimuth: float | None = None
    sun_elevation: float | None = None


@dataclass
class ClimateSnapshot:
    sensors: SensorStates
    comfort: ComfortScore
    ventilation: VentilationAdvice
    fan: FanAdvice
    cover: CoverPosition
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
        """Merged config: options (set via options flow) override original data."""
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
        try:
            return float(state.state)
        except ValueError:
            return None

    def _collect_states(self) -> SensorStates:
        climate_id = self._config.get(CONF_CLIMATE_ENTITY)
        climate_state = self.hass.states.get(climate_id) if climate_id else None

        temp_indoor: float | None = None
        temp_setpoint: float | None = None
        hvac_action: str | None = None

        if climate_state and climate_state.state not in ("unavailable", "unknown"):
            attrs = climate_state.attributes
            temp_indoor = _safe_float(attrs.get("current_temperature"))
            temp_setpoint = _safe_float(attrs.get("temperature"))
            hvac_action = attrs.get("hvac_action")

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
            temp_indoor=temp_indoor,
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
        step = float(attrs.get("step", 1))
        # Guard: step == 0 causes ZeroDivisionError; treat as step 1
        if step <= 0:
            step = 1.0
        raw = min_val + (speed_pct / 100) * (max_val - min_val)
        value = max(min_val, min(max_val, round(round(raw / step) * step, 10)))
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    # ------------------------------------------------------------------
    # Cover actuator
    # ------------------------------------------------------------------

    async def _async_apply_covers(self, position: int, entity_ids: list[str]) -> None:
        for entity_id in entity_ids:
            last = self._last_cover_positions.get(entity_id, -1)
            if abs(position - last) < COVER_HYSTERESIS:
                continue
            try:
                await self.hass.services.async_call(
                    "cover",
                    "set_cover_position",
                    {"entity_id": entity_id, "position": position},
                    blocking=True,
                )
                _LOGGER.debug("Cover %s → %d%% (was %d%%)", entity_id, position, last)
                self._last_cover_positions[entity_id] = position
            except Exception as exc:
                _LOGGER.error("Fout bij aansturen cover %s: %s", entity_id, exc)

    # ------------------------------------------------------------------
    # Window helpers: temperature gate + curtain dependency
    # ------------------------------------------------------------------

    def _window_temp_allowed(self, states: SensorStates) -> bool:
        """Return True if outdoor temperature permits opening windows.

        CO2 critical always overrides the temperature gate — fresh air is
        needed even if it's cold or hot outside.
        """
        if states.temp_outdoor is None:
            return True  # no sensor configured, allow opening

        temp_min = float(self._config.get(CONF_WINDOW_TEMP_MIN, DEFAULT_WINDOW_TEMP_MIN))
        temp_max = float(self._config.get(CONF_WINDOW_TEMP_MAX, DEFAULT_WINDOW_TEMP_MAX))

        if temp_min <= states.temp_outdoor <= temp_max:
            return True

        # Outside the comfort range — block unless CO2 is critical
        co2_critical = states.co2 is not None and states.co2 > CO2_POOR
        if co2_critical:
            _LOGGER.debug(
                "Raam openen ondanks buitentemp %.1f°C — CO₂ kritiek (%.0f ppm)",
                states.temp_outdoor,
                states.co2,
            )
            return True

        _LOGGER.debug(
            "Raam openen geblokkeerd: buitentemp %.1f°C buiten bereik [%.0f–%.0f °C]",
            states.temp_outdoor,
            temp_min,
            temp_max,
        )
        return False

    async def _async_apply_window_with_curtain(
        self,
        window_id: str,
        target_position: int,
    ) -> None:
        """Open/close a window while honouring its paired curtain.

        Rules:
        • Window wants to open → curtain must be at least `curtain_min_open` %
          open. If it isn't, open the curtain first (to minimum), then open window.
        • Window wants to close → curtain is not touched (user may have it
          positioned deliberately).
        • Curtain is fully closed (< 5 %) → window is limited to 0 regardless of
          target, to avoid damage from the curtain being pulled in by suction.
        """
        curtain_map: dict = self._config.get(CONF_WINDOW_CURTAIN_MAP) or {}
        curtain_id: str | None = curtain_map.get(window_id)
        min_curtain = float(self._config.get(CONF_CURTAIN_MIN_OPEN, DEFAULT_CURTAIN_MIN_OPEN))

        if curtain_id and target_position > 0:
            curtain_state = self.hass.states.get(curtain_id)
            curtain_pos: float | None = None

            if curtain_state and curtain_state.state not in ("unavailable", "unknown"):
                curtain_pos = curtain_state.attributes.get("current_position")
                if curtain_pos is not None:
                    curtain_pos = float(curtain_pos)

            if curtain_pos is not None:
                if curtain_pos < 5:
                    # Curtain fully closed — opening window would pull/damage it
                    _LOGGER.debug(
                        "Raam %s geblokkeerd: gordijn %s volledig dicht (%.0f%%)",
                        window_id, curtain_id, curtain_pos,
                    )
                    target_position = 0

                elif curtain_pos < min_curtain:
                    # Curtain almost closed — open it to minimum before opening window
                    _LOGGER.debug(
                        "Gordijn %s naar %.0f%% voor ventilatie via raam %s",
                        curtain_id, min_curtain, window_id,
                    )
                    try:
                        await self.hass.services.async_call(
                            "cover",
                            "set_cover_position",
                            {"entity_id": curtain_id, "position": int(min_curtain)},
                            blocking=True,
                        )
                    except Exception as exc:
                        _LOGGER.error("Gordijn %s aansturen mislukt: %s", curtain_id, exc)
                        # Don't open window if curtain couldn't be moved
                        target_position = 0

        await self._async_apply_covers(target_position, [window_id])

    async def _async_apply_windows(
        self, base_position: int, states: SensorStates
    ) -> None:
        """Apply window positions with temperature gate and curtain handling."""
        window_ids: list[str] = list(self._config.get(CONF_WINDOW_ENTITIES) or [])
        if not window_ids:
            return

        effective = base_position
        if effective > 0 and not self._window_temp_allowed(states):
            effective = 0

        for window_id in window_ids:
            await self._async_apply_window_with_curtain(window_id, effective)

    # ------------------------------------------------------------------
    # Mode-aware action dispatch
    # ------------------------------------------------------------------

    async def _async_apply_actions(
        self, fan: FanAdvice, cover: CoverPosition, states: SensorStates
    ) -> None:
        """Apply actuator commands respecting the current mode."""

        if self.mode == MODE_AWAY:
            await self._async_apply_fan(FAN_MIN_SPEED)
            await self._async_apply_covers(
                _COVER_AWAY_POSITION,
                list(self._config.get(CONF_COVER_ENTITIES) or []),
            )
            # Windows use curtain-aware close so curtains aren't yanked shut
            await self._async_apply_windows(0, states)
            return

        if self.mode == MODE_SLEEP:
            sleep_fan = min(fan.speed_pct, 50)
            await self._async_apply_fan(sleep_fan)
            await self._async_apply_covers(
                _COVER_SLEEP_POSITION,
                list(self._config.get(CONF_COVER_ENTITIES) or []),
            )
            await self._async_apply_windows(0, states)
            return

        if self.mode != MODE_AUTO:
            # Manual mode: read-only, no actuator writes
            return

        # Auto mode
        await self._async_apply_fan(fan.speed_pct)
        await self._async_apply_covers(
            cover.position,
            self._config.get(CONF_COVER_ENTITIES) or [],
        )
        # Windows open when ventilation is needed, gated by temp + curtains
        window_position = 100 if fan.speed_pct > FAN_MIN_SPEED else 0
        await self._async_apply_windows(window_position, states)

    def _all_cover_entity_ids(self) -> list[str]:
        covers = self._config.get(CONF_COVER_ENTITIES) or []
        windows = self._config.get(CONF_WINDOW_ENTITIES) or []
        return list(covers) + list(windows)

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

        cover = cover_algo.calculate(
            sun_azimuth=states.sun_azimuth or 0.0,
            sun_elevation=states.sun_elevation or -1.0,
            window_azimuth=float(
                self._config.get(CONF_WINDOW_AZIMUTH, DEFAULT_WINDOW_AZIMUTH)
            ),
            season=season,
            window_fov=float(
                self._config.get(CONF_WINDOW_FOV, DEFAULT_WINDOW_FOV)
            ),
        )

        await self._async_apply_actions(fan, cover, states)

        return ClimateSnapshot(
            sensors=states,
            comfort=comfort,
            ventilation=ventilation,
            fan=fan,
            cover=cover,
            mode=self.mode,
            co2_history=list(self._co2_history),
        )
