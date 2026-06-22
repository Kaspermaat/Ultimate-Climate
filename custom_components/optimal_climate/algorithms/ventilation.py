"""Ventilation advice based on CO2 and humidity levels."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VentilationReason(StrEnum):
    CO2_CRITICAL = "co2_critical"
    CO2_ELEVATED = "co2_elevated"
    CO2_OK = "co2_ok"
    HUMIDITY_HIGH = "humidity_high"
    HUMIDITY_OUTDOOR_TOO_WET = "humidity_outdoor_too_wet"
    NO_DATA = "no_data"


@dataclass(frozen=True)
class VentilationAdvice:
    should_ventilate: bool
    intensity: int          # 0-100 (%)
    reason: VentilationReason
    priority: int           # 0 = low, 1 = normal, 2 = urgent

    @property
    def label(self) -> str:
        labels = {
            VentilationReason.CO2_CRITICAL: "CO₂ kritiek — max ventilatie",
            VentilationReason.CO2_ELEVATED: "CO₂ verhoogd — ventileer",
            VentilationReason.CO2_OK: "CO₂ goed",
            VentilationReason.HUMIDITY_HIGH: "Vochtigheid te hoog — ventileer",
            VentilationReason.HUMIDITY_OUTDOOR_TOO_WET: "Buiten te vochtig om te ventileren",
            VentilationReason.NO_DATA: "Geen sensordata",
        }
        return labels[self.reason]


def calculate(
    co2: float | None,
    humidity_indoor: float | None,
    humidity_outdoor: float | None,
    co2_good: int = 800,
    co2_moderate: int = 1000,
    co2_poor: int = 1200,
    humidity_outdoor_margin: int = 10,
) -> VentilationAdvice:
    """Return ventilation advice.

    Outdoor humidity check wins over CO2 only when CO2 is not yet critical,
    preventing the integration from making the house damp to chase a moderate
    CO2 reading.
    """
    # CO2 critical always overrides humidity check
    if co2 is not None and co2 > co2_poor:
        return VentilationAdvice(
            should_ventilate=True,
            intensity=100,
            reason=VentilationReason.CO2_CRITICAL,
            priority=2,
        )

    # Skip ventilation if outdoor air would make inside more humid
    if (
        humidity_indoor is not None
        and humidity_outdoor is not None
        and humidity_outdoor > humidity_indoor + humidity_outdoor_margin
    ):
        return VentilationAdvice(
            should_ventilate=False,
            intensity=0,
            reason=VentilationReason.HUMIDITY_OUTDOOR_TOO_WET,
            priority=0,
        )

    if co2 is not None:
        if co2 > co2_moderate:
            return VentilationAdvice(
                should_ventilate=True,
                intensity=60,
                reason=VentilationReason.CO2_ELEVATED,
                priority=1,
            )
        if co2 <= co2_good:
            return VentilationAdvice(
                should_ventilate=False,
                intensity=0,
                reason=VentilationReason.CO2_OK,
                priority=0,
            )

    if humidity_indoor is not None and humidity_indoor > 70:
        return VentilationAdvice(
            should_ventilate=True,
            intensity=50,
            reason=VentilationReason.HUMIDITY_HIGH,
            priority=1,
        )

    return VentilationAdvice(
        should_ventilate=False,
        intensity=0,
        reason=VentilationReason.NO_DATA,
        priority=0,
    )
