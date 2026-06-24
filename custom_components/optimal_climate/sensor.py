"""Sensor entities exposed by the Optimal Climate integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONE_NAME, DOMAIN
from .coordinator import ClimateSnapshot, CoverResult, OptimalClimateCoordinator

_REASON_LABELS: dict[str, str] = {
    # Raam-specifiek
    "regen":                    "regen — raam dicht",
    "harde_wind":               "harde wind — raam dicht",
    "temperatuur_buiten_bereik":"buitentemperatuur buiten bereik",
    "airco_actief":             "airco actief — raam dicht",
    "verwarming_actief":        "thermostaat verwarmt — raam dicht",
    "natuurlijke_koeling":      "natuurlijke koeling — raam open, airco uit",
    "gordijn_dicht":            "gordijn geblokkeerd",
    "ventilatie":               "open voor ventilatie",
    # Shutter/gordijn
    "bewolkt":                  "te bewolkt — zonwering niet nodig",
    "zonwering_uit":            "zonwering uitgeschakeld",
    "zonwering":                "zon bescherming actief",
    "tussenseizoenen_gedeeltelijk": "gedeeltelijk — tussenseizoenen",
    "lichtsterkte_hoog_geforceerd": "felle zon — zonwering geforceerd",
    "lichtsterkte_laag":        "weinig licht — open",
    "zon_niet_in_zicht":        "zon niet op dit raam — open",
    "zon_onder_horizon":        "nacht — open",
    "winter_passieve_opwarming":"winter — zon binnen laten",
    # Overig
    "geforceerd":               "geforceerd door modus",
}


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
            CoversSummarySensor(coordinator, entry, zone),
            ActivityLogSensor(coordinator, entry, zone),
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


class CoversSummarySensor(_BaseClimateSensor):
    """Toont het aantal actieve covers en hun gemiddelde positie."""

    _attr_name = "Covers overzicht"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:window-shutter"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "covers_summary")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None or not self.coordinator.data.covers:
            return None
        positions = [c.position for c in self.coordinator.data.covers]
        return int(sum(positions) / len(positions))

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        s = self.coordinator.data.sensors
        return {
            "covers": [
                {"entity": c.entity_id, "positie": c.position, "reden": c.reason}
                for c in self.coordinator.data.covers
            ],
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


class ActivityLogSensor(_BaseClimateSensor):
    """Laat in leesbare tekst zien wat de integratie doet en waarom."""

    _attr_name = "Activiteiten log"
    _attr_icon = "mdi:clipboard-text-outline"

    def __init__(self, coordinator, entry, zone):
        super().__init__(coordinator, entry, zone, "activity_log")

    def _friendly(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        if state:
            return state.attributes.get("friendly_name") or entity_id
        return entity_id

    def _cover_status(self, position: int) -> str:
        if position >= 90:
            return "open"
        if position >= 50:
            return "half open"
        if position >= 10:
            return "grotendeels dicht"
        return "gesloten"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        snap = self.coordinator.data
        s = snap.sensors

        # Meest opvallende weerconditie als prefix
        weather_prefix = ""
        if s.rain_active:
            weather_prefix = "regen"
        elif s.wind_too_strong:
            spd = f" {s.wind_speed:.0f} km/h" if s.wind_speed else ""
            weather_prefix = f"harde wind{spd}"
        elif s.heavily_overcast:
            weather_prefix = f"bewolkt {s.cloud_coverage}%"

        if not snap.covers:
            return weather_prefix or "geen covers geconfigureerd"

        # Compacte samenvatting per cover: "Raam woonkamer open (ventilatie)"
        parts = []
        for c in snap.covers:
            name = self._friendly(c.entity_id)
            reden = _REASON_LABELS.get(str(c.reason), str(c.reason))
            status = self._cover_status(c.position)
            parts.append(f"{name}: {status} ({reden})")

        summary = " · ".join(parts)
        if weather_prefix:
            summary = f"[{weather_prefix}] {summary}"

        # HA max 255 tekens voor state
        return summary[:255]

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        snap = self.coordinator.data
        s = snap.sensors

        # Per-cover detailregel
        cover_details = []
        for c in snap.covers:
            name = self._friendly(c.entity_id)
            reden = _REASON_LABELS.get(str(c.reason), str(c.reason))
            cover_details.append({
                "naam": name,
                "entity_id": c.entity_id,
                "positie_pct": c.position,
                "status": self._cover_status(c.position),
                "reden": reden,
            })

        # Weer
        weer: dict = {}
        if s.weather_entity:
            weer = {
                "bron": s.weather_entity,
                "conditie": s.weather_condition,
                "wind_kmh": round(s.wind_speed, 1) if s.wind_speed is not None else None,
                "bewolking_pct": s.cloud_coverage,
                "regen_actief": s.rain_active,
                "wind_te_hard": s.wind_too_strong,
                "zwaar_bewolkt": s.heavily_overcast,
            }

        # Sensoren
        sensoren = {
            "ideale_temp_c": s.ideal_temp,
            "temp_binnen_c": s.temp_indoor,
            "temp_buiten_c": s.temp_outdoor,
            "co2_ppm": s.co2,
            "vochtigheid_binnen_pct": s.humidity_indoor,
            "vochtigheid_buiten_pct": s.humidity_outdoor,
            "zon_azimuth": s.sun_azimuth,
            "zon_elevatie": s.sun_elevation,
        }

        # Airco-status
        klimaat = {
            "airco_koelt_actief": s.ac_actively_cooling,
            "verwarming_actief": s.heating_active,
            "natuurlijke_koeling_mogelijk": s.natural_cooling_possible,
            "modus": snap.mode,
        }

        return {
            "covers": cover_details,
            "weer": weer,
            "sensoren": sensoren,
            "klimaat": klimaat,
        }
