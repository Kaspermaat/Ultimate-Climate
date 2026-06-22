"""Optimal Climate — holistische klimaatcoördinatie voor Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS, SERVICE_RECALCULATE
from .coordinator import OptimalClimateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = OptimalClimateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Herlaad de coordinator als de opties wijzigen (via options flow)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Registreer services eenmalig (bij de eerste geladen zone)
    if not hass.services.has_service(DOMAIN, SERVICE_RECALCULATE):
        _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Verwijder services als er geen zones meer zijn
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)

    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Herlaad de config entry na een options-flow update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    async def handle_recalculate(call: ServiceCall) -> None:
        """Forceer een directe herberekening voor alle of één specifieke zone."""
        entry_id: str | None = call.data.get("config_entry_id")
        coordinators = hass.data.get(DOMAIN, {})

        if entry_id:
            coordinator = coordinators.get(entry_id)
            if coordinator:
                await coordinator.async_request_refresh()
            else:
                _LOGGER.warning("Geen zone gevonden met entry_id '%s'", entry_id)
        else:
            # Geen specifieke zone → herbereken alle zones
            for coordinator in coordinators.values():
                await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALCULATE,
        handle_recalculate,
    )
