"""Mode select entity — lets the user switch between auto/manual/away/sleep."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_ZONE_NAME, DOMAIN, MODE_AUTO
from .coordinator import OptimalClimateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OptimalClimateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ClimateModeSelect(coordinator, entry)])


class ClimateModeSelect(RestoreEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Modus"
    _attr_icon = "mdi:home-clock"
    _attr_options = ["auto", "handmatig", "afwezig", "slaap"]

    def __init__(self, coordinator: OptimalClimateCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_mode"
        zone = entry.data[CONF_ZONE_NAME]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Optimal Climate — {zone}",
        )

    @property
    def current_option(self) -> str:
        return self._coordinator.mode

    async def async_select_option(self, option: str) -> None:
        self._coordinator.mode = option
        self.async_write_ha_state()
        # Trigger an immediate recalculation so covers/fan respond right away
        await self._coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """Restore mode from last known state after HA restart."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in self._attr_options:
            self._coordinator.mode = last.state
