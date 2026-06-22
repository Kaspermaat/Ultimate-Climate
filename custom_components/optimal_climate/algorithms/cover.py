"""Cover/shutter position based on solar angle and season."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .fan import Season


class CoverReason(StrEnum):
    SUN_BELOW_HORIZON = "zon_onder_horizon"
    SUN_NOT_IN_VIEW = "zon_niet_in_zicht"
    WINTER_PASSIVE_HEAT = "winter_passieve_opwarming"
    SUN_PROTECTION = "zonwering"
    INTERMEDIATE_PARTIAL = "tussenseizoenen_gedeeltelijk"


@dataclass(frozen=True)
class CoverPosition:
    position: int           # 0 = gesloten, 100 = open (HA conventie)
    reason: CoverReason

    @property
    def label(self) -> str:
        labels = {
            CoverReason.SUN_BELOW_HORIZON: "Open — nacht",
            CoverReason.SUN_NOT_IN_VIEW: "Open — zon niet op dit raam",
            CoverReason.WINTER_PASSIVE_HEAT: "Open — passieve zonnewarmte",
            CoverReason.SUN_PROTECTION: "Zonwering actief",
            CoverReason.INTERMEDIATE_PARTIAL: "Gedeeltelijk — tussenseizoenen",
        }
        return labels[self.reason]


def _angular_diff(a: float, b: float) -> float:
    """Smallest signed difference between two compass angles (result in [0, 180])."""
    return abs((a - b + 180) % 360 - 180)


def calculate(
    sun_azimuth: float,
    sun_elevation: float,
    window_azimuth: float,
    season: Season,
    window_fov: float = 90.0,
) -> CoverPosition:
    """Return the advised cover position for one window.

    Args:
        sun_azimuth:    compass degrees of the sun (0=N, 90=E, 180=S, 270=W)
        sun_elevation:  degrees above horizon (negative = below)
        window_azimuth: compass direction the window faces (180 = south-facing)
        season:         derived from outdoor temperature
        window_fov:     half-angle (degrees) of the window's "view cone"; default
                        90° means the sun must be within ±90° of the window normal
    """
    # Night — always open
    if sun_elevation <= 0:
        return CoverPosition(position=100, reason=CoverReason.SUN_BELOW_HORIZON)

    # Sun not shining on this window — open
    if _angular_diff(sun_azimuth, window_azimuth) > window_fov:
        return CoverPosition(position=100, reason=CoverReason.SUN_NOT_IN_VIEW)

    # Winter: let sunlight in for passive heating
    if season == Season.WINTER:
        return CoverPosition(position=100, reason=CoverReason.WINTER_PASSIVE_HEAT)

    # Sun is hitting the window — calculate closure
    # Two factors drive how much to close:
    # • elevation_ratio  — higher sun (more overhead) = more direct = close more
    # • centering_ratio  — sun directly in front of window = close more
    elevation_ratio = min(1.0, sun_elevation / 70.0)   # full effect at 70° elev
    centering_ratio = 1.0 - (_angular_diff(sun_azimuth, window_azimuth) / window_fov)
    closure = elevation_ratio * centering_ratio         # 0.0 – 1.0

    if season == Season.INTERMEDIATE:
        closure *= 0.5
        position = int(100 - closure * 80)
        return CoverPosition(position=max(20, position), reason=CoverReason.INTERMEDIATE_PARTIAL)

    # Summer: close up to 90% (never fully shut — keep some daylight + air)
    position = int(100 - closure * 90)
    return CoverPosition(position=max(10, position), reason=CoverReason.SUN_PROTECTION)
