from pathlib import Path

import pytest

from fleet.config import load_config
from fleet.vehicle import signals
from fleet.vehicle.detector import Detector
from fleet.vehicle.twin import InMemoryTwin
from tests.harness.clock import FakeClock

pytestmark = pytest.mark.standin
CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
CALM = {
    signals.SPEED: 40.0,
    signals.ACCEL: 0.0,
    signals.TRACTION: False,
    signals.SOC: 60.0,
    signals.COOLANT: 70.0,
}
HAZARD = [signals.HAZARD_TYPE, signals.HAZARD_SEVERITY, signals.HAZARD_T0]


@pytest.fixture
async def setup():
    twin, clock = InMemoryTwin(signals.ALL), FakeClock()
    await Detector(twin, 50.0, CFG.thresholds, clock).start()
    await twin.set(CALM)
    return twin, clock


async def hazard(twin):
    return tuple((await twin.get(HAZARD)).values())


async def test_req050_starts_with_no_hazard(setup):
    twin, _clock = setup

    assert (await hazard(twin))[:2] == ("none", 0)


async def test_req050_hard_brake_writes_critical_with_t0(setup):
    twin, clock = setup
    clock.ms += 5000

    await twin.set({signals.ACCEL: -7.5})

    assert await hazard(twin) == ("harsh_braking", 3, clock.ms)


async def test_req050_unchanged_hazard_keeps_t0(setup):
    twin, clock = setup
    await twin.set({signals.ACCEL: -7.5})
    t0 = clock.ms
    clock.ms += 300

    await twin.set({signals.ACCEL: -7.6, signals.SPEED: 30.0})

    assert await hazard(twin) == ("harsh_braking", 3, t0)


async def test_req050_escalation_rewrites_with_new_t0(setup):
    twin, clock = setup
    await twin.set({signals.ACCEL: -5.0})
    clock.ms += 200

    await twin.set({signals.ACCEL: -7.2})

    assert await hazard(twin) == ("harsh_braking", 3, clock.ms)


async def test_req050_clearing_writes_none(setup):
    twin, clock = setup
    await twin.set({signals.ACCEL: -7.5})
    clock.ms += 1000

    await twin.set({signals.ACCEL: 0.0})

    assert await hazard(twin) == ("none", 0, clock.ms)


async def test_req050_uses_route_limit_for_overspeed(setup):
    twin, _clock = setup

    await twin.set({signals.SPEED: 60.5})

    assert (await hazard(twin))[:2] == ("overspeed", 1)
