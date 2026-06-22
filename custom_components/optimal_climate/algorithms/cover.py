"""Cover/shutter position based on solar angle, season, and illuminance."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .fan import Season


class CoverReason(StrEnum):
    SUN_BELOW_HORIZON = "zon_onder_horizon"
    SUN_NOT_IN_VIEW = "zon_niet_in_zicht"
    WINTER_PASSIVE_HEAT = "winter_passieve_opwarming"
    ILLUMINANCE_LOW = "lichtsterkte_laag"
    SUN_PROTECTION = "zonwering"
    INTERMEDIATE_PARTIAL = "tussenseizoenen_gedeeltelijk"
    ILLUMINANCE_FORCED = "lichtsterkte_hoog_geforceerd"


@dataclass(frozen=True)
class CoverPosition:
    position: int           # 0 = gesloten, 100 = open (HA-conventie)
    reason: CoverReason

    @property
    def label(self) -> str:
        labels = {
            CoverReason.SUN_BELOW_HORIZON: "Open — nacht",
            CoverReason.SUN_NOT_IN_VIEW: "Open — zon niet op dit raam",
            CoverReason.WINTER_PASSIVE_HEAT: "Open — passieve zonnewarmte",
            CoverReason.ILLUMINANCE_LOW: "Open — lichtsterkte laag",
            CoverReason.SUN_PROTECTION: "Zonwering actief",
            CoverReason.INTERMEDIATE_PARTIAL: "Gedeeltelijk — tussenseizoenen",
            CoverReason.ILLUMINANCE_FORCED: "Zonwering — hoge lichtsterkte",
        }
        return labels[self.reason]


def _angular_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def calculate(
    sun_azimuth: float,
    sun_elevation: float,
    window_azimuth: float,
    season: Season,
    window_fov: float = 90.0,
    min_position: int = 0,
    illuminance: float | None = None,
    illuminance_threshold: float = 10000.0,
) -> CoverPosition:
    """Return the advised cover position for one cover/shutter.

    Decision order:
    1. Night or winter passive heating → open
    2. Illuminance sensor available + very bright → force protection
    3. Sun angle says protect → calculate closure
    4. Illuminance sensor says not bright enough → open despite angle
    5. Apply min_position floor (cover never goes below this % open)

    Args:
        min_position: floor on position — e.g. 15 means never more than
                      85% closed (the cover stays ≥ 15% open).
    """
    # 1a — Night
    if sun_elevation <= 0:
        return CoverPosition(position=100, reason=CoverReason.SUN_BELOW_HORIZON)

    # 1b — Sun not aimed at this cover
    angle_diff = _angular_diff(sun_azimuth, window_azimuth)
    if angle_diff > window_fov:
        return CoverPosition(position=100, reason=CoverReason.SUN_NOT_IN_VIEW)

    # 1c — Winter: let sun in for passive heating
    if season == Season.WINTER:
        return CoverPosition(position=100, reason=CoverReason.WINTER_PASSIVE_HEAT)

    # 2 — Illuminance-forced protection: sensor present and very bright
    #     (overrides angle-based "not quite facing" doubts)
    if illuminance is not None and illuminance >= illuminance_threshold:
        target = _angle_based_position(angle_diff, window_fov, sun_elevation, season)
        final = max(min_position, target)
        return CoverPosition(position=final, reason=CoverReason.ILLUMINANCE_FORCED)

    # 3 — Sun angle says protect
    target = _angle_based_position(angle_diff, window_fov, sun_elevation, season)

    # 4 — Illuminance too low to bother protecting despite angle
    if illuminance is not None and illuminance < illuminance_threshold * 0.4:
        return CoverPosition(position=100, reason=CoverReason.ILLUMINANCE_LOW)

    # 5 — Apply min_position floor
    final = max(min_position, target)
    reason = (
        CoverReason.INTERMEDIATE_PARTIAL
        if season == Season.INTERMEDIATE
        else CoverReason.SUN_PROTECTION
    )
    return CoverPosition(position=final, reason=reason)


def _angle_based_position(
    angle_diff: float,
    window_fov: float,
    sun_elevation: float,
    season: Season,
) -> int:
    """Calculate raw closure based on sun geometry alone (no floor applied)."""
    elevation_ratio = min(1.0, sun_elevation / 70.0)
    centering_ratio = 1.0 - (angle_diff / window_fov)
    closure = elevation_ratio * centering_ratio

    if season == Season.INTERMEDIATE:
        closure *= 0.5
        return int(100 - closure * 80)

    # Summer: up to 90% closed
    return int(100 - closure * 90)
