"""Hazard rules from the brief (spec REQ-020/021). Pure: no I/O, no clock."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from fleet.config import Thresholds


class HazardType(StrEnum):
    HARSH_BRAKING = "harsh_braking"
    TRACTION_LOSS = "traction_loss"
    OVERHEAT = "overheat"
    LOW_ENERGY = "low_energy"
    OVERSPEED = "overspeed"


class Severity(IntEnum):
    WARNING = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(frozen=True)
class Signals:
    speed_kmh: float
    accel_ms2: float
    traction_active: bool
    coolant_c: float
    soc_pct: float


@dataclass(frozen=True)
class Hazard:
    type: HazardType
    severity: Severity


def evaluate(s: Signals, speed_limit_kmh: float, t: Thresholds) -> list[Hazard]:
    fired = []
    decel_ms2 = -s.accel_ms2
    if decel_ms2 >= t.brake_critical_ms2:
        fired.append(Hazard(HazardType.HARSH_BRAKING, Severity.CRITICAL))
    elif decel_ms2 >= t.brake_high_ms2:
        fired.append(Hazard(HazardType.HARSH_BRAKING, Severity.HIGH))
    if s.traction_active and s.speed_kmh >= t.traction_min_speed_kmh:
        fired.append(Hazard(HazardType.TRACTION_LOSS, Severity.CRITICAL))
    if s.coolant_c > t.coolant_high_c:
        fired.append(Hazard(HazardType.OVERHEAT, Severity.HIGH))
    if s.soc_pct <= t.soc_high_pct:
        fired.append(Hazard(HazardType.LOW_ENERGY, Severity.HIGH))
    elif s.soc_pct <= t.soc_warning_pct:
        fired.append(Hazard(HazardType.LOW_ENERGY, Severity.WARNING))
    if s.speed_kmh > speed_limit_kmh + t.overspeed_margin_kmh:
        fired.append(Hazard(HazardType.OVERSPEED, Severity.WARNING))
    return fired


def most_severe(hazards: list[Hazard], tie_break: tuple[str, ...]) -> Hazard | None:
    """Highest severity wins; equal severities go to the type listed first in tie_break."""
    if not hazards:
        return None
    return min(hazards, key=lambda h: (-h.severity, tie_break.index(h.type)))
