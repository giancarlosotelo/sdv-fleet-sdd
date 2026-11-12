from dataclasses import replace
from pathlib import Path

import pytest

from fleet.config import HAZARD_TYPES, load_config
from fleet.vehicle.rules import Hazard, HazardType, Severity, Signals, evaluate, most_severe

THRESHOLDS = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml").thresholds
CALM = Signals(speed_kmh=40.0, accel_ms2=0.0, traction_active=False, coolant_c=70.0, soc_pct=60.0)
LIMIT_KMH = 50.0


def fired(**changes) -> list[Hazard]:
    return evaluate(replace(CALM, **changes), LIMIT_KMH, THRESHOLDS)


def test_req020_calm_driving_fires_nothing():
    assert fired() == []


@pytest.mark.parametrize(
    ("accel_ms2", "expected"),
    [(-3.99, None), (-4.0, Severity.HIGH), (-6.99, Severity.HIGH), (-7.0, Severity.CRITICAL)],
)
def test_req020_harsh_braking_boundaries(accel_ms2, expected):
    hazards = fired(accel_ms2=accel_ms2)

    assert hazards == ([Hazard(HazardType.HARSH_BRAKING, expected)] if expected else [])


@pytest.mark.parametrize(
    ("speed_kmh", "expected"), [(19.99, None), (20.0, Severity.CRITICAL), (45.0, Severity.CRITICAL)]
)
def test_req020_traction_loss_needs_speed(speed_kmh, expected):
    hazards = fired(traction_active=True, speed_kmh=speed_kmh)

    assert hazards == ([Hazard(HazardType.TRACTION_LOSS, expected)] if expected else [])


def test_req020_traction_inactive_at_speed_fires_nothing():
    assert fired(traction_active=False, speed_kmh=45.0) == []


@pytest.mark.parametrize(("coolant_c", "expected"), [(90.0, None), (90.01, Severity.HIGH)])
def test_req020_overheat_is_strictly_above_90(coolant_c, expected):
    hazards = fired(coolant_c=coolant_c)

    assert hazards == ([Hazard(HazardType.OVERHEAT, expected)] if expected else [])


@pytest.mark.parametrize(
    ("soc_pct", "expected"),
    [(20.01, None), (20.0, Severity.WARNING), (10.01, Severity.WARNING), (10.0, Severity.HIGH)],
)
def test_req020_low_energy_boundaries(soc_pct, expected):
    hazards = fired(soc_pct=soc_pct)

    assert hazards == ([Hazard(HazardType.LOW_ENERGY, expected)] if expected else [])


@pytest.mark.parametrize(("speed_kmh", "expected"), [(60.0, None), (60.01, Severity.WARNING)])
def test_req020_overspeed_is_strictly_above_limit_plus_10(speed_kmh, expected):
    hazards = fired(speed_kmh=speed_kmh)

    assert hazards == ([Hazard(HazardType.OVERSPEED, expected)] if expected else [])


def test_req020_thresholds_come_from_config():
    stricter = replace(THRESHOLDS, brake_high_ms2=3.0, coolant_high_c=80.0)

    hazards = evaluate(replace(CALM, accel_ms2=-3.5, coolant_c=85.0), LIMIT_KMH, stricter)

    assert hazards == [
        Hazard(HazardType.HARSH_BRAKING, Severity.HIGH),
        Hazard(HazardType.OVERHEAT, Severity.HIGH),
    ]


def test_req021_most_severe_wins():
    hazards = fired(accel_ms2=-8.0, soc_pct=15.0)

    assert most_severe(hazards, THRESHOLDS.tie_break) == Hazard(
        HazardType.HARSH_BRAKING, Severity.CRITICAL
    )


def test_req021_no_hazards_gives_none():
    assert most_severe([], THRESHOLDS.tie_break) is None


@pytest.mark.parametrize(
    ("order", "winner"),
    [
        (("traction_loss", "harsh_braking"), HazardType.TRACTION_LOSS),
        (("harsh_braking", "traction_loss"), HazardType.HARSH_BRAKING),
    ],
)
def test_req021_equal_severity_follows_tie_break(order, winner):
    hazards = fired(accel_ms2=-7.5, traction_active=True, speed_kmh=30.0)

    assert most_severe(hazards, order) == Hazard(winner, Severity.CRITICAL)


def test_req021_severity_beats_tie_break_order():
    hazards = fired(accel_ms2=-8.0, soc_pct=15.0)
    low_energy_first = ("low_energy", "harsh_braking", "traction_loss", "overheat", "overspeed")

    assert most_severe(hazards, low_energy_first) == Hazard(
        HazardType.HARSH_BRAKING, Severity.CRITICAL
    )


def test_req021_config_hazard_list_matches_rules():
    assert sorted(HAZARD_TYPES) == sorted(HazardType)
