"""Virtuele hoofdthermostaat — centrale aansturing voor Optimal Climate.

De gebruiker stelt hier de doeltemperatuur en modus in. De coordinator
leest deze waarden en regelt vervolgens de echte thermostaten, airco en
alle covers (ramen, shutters, gordijnen) om de ideale temperatuur te halen.
"""
from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PRECISION_HALVES, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_IDEAL_TEMP,
    CONF_ZONE_NAME,
    DEFAULT_IDEAL_TEMP,
    DOMAIN,
    MODE_AUTO,
    MODE_AWAY,
    MODE_SLEEP,
)
from .coordinator import OptimalClimateCoordinator

# HA preset-namen (strings)
_PRESET_NONE  = "normaal"
_PRESET_AWAY  = "afwezig"
_PRESET_SLEEP = "slaap"

# Mapping preset → interne modus
_PRESET_TO_MODE = {
    _PRESET_NONE:  MODE_AUTO,
    _PRESET_AWAY:  MODE_AWAY,
    _PRESET_SLEEP: MODE_SLEEP,
}
_MODE_TO_PRESET = {v: k for k, v in _PRESET_TO_MODE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OptimalClimateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OptimalClimateThermostat(coordinator, entry)])


class OptimalClimateThermostat(
    CoordinatorEntity[OptimalClimateCoordinator],
    ClimateEntity,
    RestoreEntity,
):
    """Virtuele hoofdthermostaat die alle klimaatactuatoren aanstuurt."""

    _attr_has_entity_name = True
    _attr_name = "Thermostaat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_HALVES
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16.0
    _attr_max_temp = 28.0
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_preset_modes = [_PRESET_NONE, _PRESET_AWAY, _PRESET_SLEEP]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_icon = "mdi:home-thermometer"

    def __init__(
        self,
        coordinator: OptimalClimateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        zone = entry.data[CONF_ZONE_NAME]
        self._attr_unique_id = f"{entry.entry_id}_main_thermostat"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Optimal Climate — {zone}",
            manufacturer="Optimal Climate",
            model="Klimaatcoördinator",
            entry_type="service",
        )
        # Initiële waarden — worden overschreven door RestoreEntity
        default_temp = float(
            entry.options.get(CONF_IDEAL_TEMP)
            or entry.data.get(CONF_IDEAL_TEMP)
            or DEFAULT_IDEAL_TEMP
        )
        self._target_temp: float = default_temp
        self._hvac_mode: HVACMode = HVACMode.HEAT_COOL
        # Coordinator bijwerken met initiële waarden
        coordinator.ideal_temp = default_temp
        coordinator.mode = MODE_AUTO

    # ------------------------------------------------------------------
    # Restore state across restarts
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            # HVAC mode
            try:
                self._hvac_mode = HVACMode(last.state)
            except ValueError:
                self._hvac_mode = HVACMode.HEAT_COOL

            # Target temperature
            if (t := last.attributes.get("temperature")) is not None:
                try:
                    self._target_temp = float(t)
                except (TypeError, ValueError):
                    pass

            # Preset → modus
            preset = last.attributes.get("preset_mode", _PRESET_NONE)
            self.coordinator.mode = _PRESET_TO_MODE.get(preset, MODE_AUTO)

            # Coordinator bijwerken
            if self._hvac_mode == HVACMode.OFF:
                self.coordinator.mode = "uit"
            self.coordinator.ideal_temp = self._target_temp

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode:
        return self._hvac_mode

    @property
    def target_temperature(self) -> float:
        return self._target_temp

    @property
    def current_temperature(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.sensors.temp_indoor

    @property
    def preset_mode(self) -> str:
        return _MODE_TO_PRESET.get(self.coordinator.mode, _PRESET_NONE)

    @property
    def hvac_action(self) -> str | None:
        """Toon wat er nu feitelijk gebeurt."""
        if self._hvac_mode == HVACMode.OFF:
            return "off"
        if self.coordinator.data is None:
            return "idle"
        s = self.coordinator.data.sensors
        if s.ac_actively_cooling:
            return "cooling"
        # Controleer of thermostaat verwarmt
        if s.climate_hvac_action == "heating":
            return "heating"
        return "idle"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        self._target_temp = float(temp)
        self.coordinator.ideal_temp = self._target_temp
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._hvac_mode = hvac_mode
        if hvac_mode == HVACMode.OFF:
            self.coordinator.mode = "uit"
        else:
            # Herstel vanuit preset
            preset = self.preset_mode
            self.coordinator.mode = _PRESET_TO_MODE.get(preset, MODE_AUTO)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode = _PRESET_TO_MODE.get(preset_mode, MODE_AUTO)
        self.coordinator.mode = mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
