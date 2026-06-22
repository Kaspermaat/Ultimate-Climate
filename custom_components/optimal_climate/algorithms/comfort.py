"""Comfort score calculation — pure functions, no HA dependencies."""
from __future__ import annotations

from dataclasses import dataclass

from ..const import (
    CO2_GOOD,
    CO2_MODERATE,
    CO2_POOR,
    WEIGHT_CO2,
    WEIGHT_HUMIDITY,
    WEIGHT_TEMP,
)


@dataclass(frozen=True)
class ComfortScore:
    total: int                  # 0-100
    co2_score: int              # 0-100
    humidity_score: int         # 0-100
    temp_score: int             # 0-100
    label: str


def _co2_score(co2: float | None) -> int:
    if co2 is None:
        return 50
    if co2 <= CO2_GOOD:
        return 100
    if co2 <= CO2_MODERATE:
        # Linear decay 100→60 from CO2_GOOD to CO2_MODERATE
        return int(100 - 40 * (co2 - CO2_GOOD) / (CO2_MODERATE - CO2_GOOD))
    if co2 <= CO2_POOR:
        # Linear decay 60→20 from CO2_MODERATE to CO2_POOR
        return int(60 - 40 * (co2 - CO2_MODERATE) / (CO2_POOR - CO2_MODERATE))
    return max(0, int(20 - (co2 - CO2_POOR) / 50))


def _humidity_score(humidity: float | None) -> int:
    """Score based on indoor relative humidity. Ideal range 40-60%."""
    if humidity is None:
        return 50
    if 40 <= humidity <= 60:
        return 100
    if humidity < 40:
        return max(0, int(100 - (40 - humidity) * 3))
    # humidity > 60
    return max(0, int(100 - (humidity - 60) * 4))


def _temp_score(temp: float | None, setpoint: float | None) -> int:
    """Score based on distance from climate setpoint. ±0.5°C = 100, ±3°C = 0."""
    if temp is None or setpoint is None:
        return 50
    delta = abs(temp - setpoint)
    if delta <= 0.5:
        return 100
    if delta >= 3.0:
        return 0
    return int(100 - (delta - 0.5) / 2.5 * 100)


def _label(score: int) -> str:
    if score >= 85:
        return "Uitstekend"
    if score >= 70:
        return "Goed"
    if score >= 50:
        return "Matig"
    if score >= 30:
        return "Slecht"
    return "Kritiek"


def calculate(
    co2: float | None,
    humidity_indoor: float | None,
    temp_indoor: float | None,
    temp_setpoint: float | None,
) -> ComfortScore:
    co2_s = _co2_score(co2)
    hum_s = _humidity_score(humidity_indoor)
    tmp_s = _temp_score(temp_indoor, temp_setpoint)

    total = int(WEIGHT_CO2 * co2_s + WEIGHT_HUMIDITY * hum_s + WEIGHT_TEMP * tmp_s)

    return ComfortScore(
        total=total,
        co2_score=co2_s,
        humidity_score=hum_s,
        temp_score=tmp_s,
        label=_label(total),
    )
