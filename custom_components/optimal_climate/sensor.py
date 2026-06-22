"""Sensor entities exposed by the Optimal Climate integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONE_NAME, DOMAIN
from .coordinator import ClimateSnapshot, OptimalClimateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OptimalClimateCoordinator = hass.data[DOMAIN][entry.entry_id]
    zone = entry.data[CONF_ZONE_NAME]

    async_add_entities(
        [
            ComfortScoreSensor(coordinator, entry, zone),
            CO2StatusSensor(coordinator, entry, zone),
            HumidityBalanceSensor(coordinator, entry, zone),
            VentilationAdviceSensor(coordinator, entry, zone),
            CO2TrendSensor(coordinator, entry, zone),
            FanSpeedSensor(coordinator, entry, zone),
            CoverPositionSensor(coordinator, entry, zone),
        ]
    )


def _device_info(entry: ConfigEntry, zone: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Optimal Climate — {zone}",
        manufacturer="Optimal Climate",
        model="Klimaatcoördinator",
        entry_type="service",
    )


class _BaseClimateSensor(CoordinatorEntity[ClimateSnapshot], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OptimalClimateCoordinator,
        entry: ConfigEntry,
        zone: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry, zone)


class ComfortScoreSensor(_BaseClimateSensor):
    _attr_name = "Comfortscore"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-thermometer"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "comfort_score")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.comfort.total

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        c = self.coordinator.data.comfort
        return {
            "label": c.label,
            "co2_score": c.co2_score,
            "vochtigheid_score": c.humidity_score,
            "temperatuur_score": c.temp_score,
        }


class CO2StatusSensor(_BaseClimateSensor):
    _attr_name = "CO₂ status"
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "co2_status")

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        co2 = self.coordinator.data.sensors.co2
        if co2 is None:
            return "onbekend"
        if co2 <= 800:
            return "goed"
        if co2 <= 1000:
            return "matig"
        if co2 <= 1200:
            return "slecht"
        return "kritiek"

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return {"co2_ppm": self.coordinator.data.sensors.co2}


class HumidityBalanceSensor(_BaseClimateSensor):
    _attr_name = "Vochtbalans"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "humidity_balance")

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        s = self.coordinator.data.sensors
        if s.humidity_indoor is None:
            return None
        if s.humidity_outdoor is None:
            return round(s.humidity_indoor, 1)
        return round(s.humidity_indoor - s.humidity_outdoor, 1)

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        s = self.coordinator.data.sensors
        return {
            "binnen": s.humidity_indoor,
            "buiten": s.humidity_outdoor,
        }


class VentilationAdviceSensor(_BaseClimateSensor):
    _attr_name = "Ventilatie advies"
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "ventilation_advice")

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.ventilation.label

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        v = self.coordinator.data.ventilation
        return {
            "ventileer": v.should_ventilate,
            "intensiteit": v.intensity,
            "prioriteit": v.priority,
            "reden": v.reason,
        }


class CO2TrendSensor(_BaseClimateSensor):
    _attr_name = "CO₂ trend"
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "co2_trend")

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.co2_trend

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return {"geschiedenis": self.coordinator.data.co2_history}


class CoverPositionSensor(_BaseClimateSensor):
    _attr_name = "Zonwering advies"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:window-shutter"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "cover_position")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.cover.position

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        c = self.coordinator.data.cover
        s = self.coordinator.data.sensors
        return {
            "label": c.label,
            "reden": c.reason,
            "zon_azimuth": s.sun_azimuth,
            "zon_elevatie": s.sun_elevation,
        }


class FanSpeedSensor(_BaseClimateSensor):
    _attr_name = "Afzuiging advies"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "fan_speed")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.fan.speed_pct

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        f = self.coordinator.data.fan
        s = self.coordinator.data.sensors
        return {
            "label": f.label,
            "reden": f.reason,
            "seizoen": f.season,
            "temp_delta": (
                round(s.temp_indoor - s.temp_outdoor, 1)
                if s.temp_indoor is not None and s.temp_outdoor is not None
                else None
            ),
        }
