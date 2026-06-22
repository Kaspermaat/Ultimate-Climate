"""Fan speed advice based on CO2, temperature differential and humidity."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FanReason(StrEnum):
    CO2_CRITICAL = "co2_kritiek"
    CO2_ELEVATED = "co2_verhoogd"
    CO2_MODERATE = "co2_matig"
    SUMMER_COOLING = "zomerkoeling"
    HUMIDITY_HIGH = "vochtigheid_hoog"
    NORMAL = "normaal"


class Season(StrEnum):
    SUMMER = "zomer"
    INTERMEDIATE = "tussenseizoenen"
    WINTER = "winter"
    UNKNOWN = "onbekend"


@dataclass(frozen=True)
class FanAdvice:
    speed_pct: int          # 0-100
    reason: FanReason
    season: Season

    @property
    def label(self) -> str:
        labels = {
            FanReason.CO2_CRITICAL: "Max afzuiging — CO₂ kritiek",
            FanReason.CO2_ELEVATED: "Hoge afzuiging — CO₂ verhoogd",
            FanReason.CO2_MODERATE: "Verhoogde afzuiging — CO₂ matig",
            FanReason.SUMMER_COOLING: "Afzuiging voor zomerkoeling",
            FanReason.HUMIDITY_HIGH: "Afzuiging — vochtigheid te hoog",
            FanReason.NORMAL: "Minimale afzuiging",
        }
        return labels[self.reason]


def detect_season(temp_outdoor: float | None) -> Season:
    if temp_outdoor is None:
        return Season.UNKNOWN
    if temp_outdoor >= 18:
        return Season.SUMMER
    if temp_outdoor >= 10:
        return Season.INTERMEDIATE
    return Season.WINTER


def _summer_cooling_speed(temp_indoor: float, temp_outdoor: float) -> int:
    """Scale 50-100% based on how much cooler it is outside."""
    delta = temp_indoor - temp_outdoor
    # delta=2 → 50%, delta=8+ → 100%
    return min(100, max(50, int(50 + delta * 8)))


def calculate(
    co2: float | None,
    temp_indoor: float | None,
    temp_outdoor: float | None,
    humidity_indoor: float | None,
    humidity_outdoor: float | None,
    co2_good: int = 800,
    co2_moderate: int = 1000,
    co2_poor: int = 1200,
    summer_cooling_delta: float = 2.0,
    humidity_outdoor_margin: int = 10,
    min_speed: int = 20,
) -> FanAdvice:
    """Return advised fan speed.

    Priority order (high → low):
    1. CO2 critical  — always max
    2. CO2 elevated  — high speed
    3. Summer cooling — outdoor significantly cooler than indoor
       (blocked if outdoor humidity is much higher than indoor)
    4. Humidity high  — medium speed
    5. CO2 moderate  — light boost
    6. Normal        — minimum speed
    """
    season = detect_season(temp_outdoor)

    # 1. CO2 critical
    if co2 is not None and co2 > co2_poor:
        return FanAdvice(speed_pct=100, reason=FanReason.CO2_CRITICAL, season=season)

    # 2. CO2 elevated
    if co2 is not None and co2 > co2_moderate:
        return FanAdvice(speed_pct=75, reason=FanReason.CO2_ELEVATED, season=season)

    # 3. Summer cooling — buiten koeler dan binnen
    if (
        season == Season.SUMMER
        and temp_indoor is not None
        and temp_outdoor is not None
        and temp_indoor - temp_outdoor >= summer_cooling_delta
    ):
        # Blokkeer als buiten significant vochtiger — dat trekt vocht naar binnen
        outdoor_too_humid = (
            humidity_outdoor is not None
            and humidity_indoor is not None
            and humidity_outdoor > humidity_indoor + humidity_outdoor_margin
        )
        if not outdoor_too_humid:
            speed = _summer_cooling_speed(temp_indoor, temp_outdoor)
            return FanAdvice(speed_pct=speed, reason=FanReason.SUMMER_COOLING, season=season)

    # 4. Vochtigheid te hoog
    if humidity_indoor is not None and humidity_indoor > 70:
        return FanAdvice(speed_pct=60, reason=FanReason.HUMIDITY_HIGH, season=season)

    # 5. CO2 matig
    if co2 is not None and co2 > co2_good:
        return FanAdvice(speed_pct=40, reason=FanReason.CO2_MODERATE, season=season)

    # 6. Normaal — altijd minimale afzuiging
    return FanAdvice(speed_pct=min_speed, reason=FanReason.NORMAL, season=season)
