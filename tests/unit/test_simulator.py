import math
import random
from pathlib import Path

import pytest

from fleet.config import load_config
from fleet.vehicle import signals
from fleet.vehicle.simulator import Simulator, run_simulator
from fleet.vehicle.twin import InMemoryTwin
from tests.harness.clock import FakeClock
from tests.harness.routes import fixture_polyline

CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
VAN = {v.id: v for v in CFG.vehicles}
DT = 0.1
pytestmark = pytest.mark.standin


def make(vid="veh-01", seed=42) -> Simulator:
    van = VAN[vid]
    return Simulator(
        van, fixture_polyline(van.route.id), CFG.charging, random.Random(f"{seed}-{vid}")
    )


def run(sim: Simulator, sim_seconds: float):
    return [sim.step(DT) for _ in range(round(sim_seconds / DT))]


def _metres(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def test_req031_same_seed_same_signals():
    assert run(make(seed=42), 300) == run(make(seed=42), 300)


def test_req031_different_seed_different_signals():
    assert run(make(seed=42), 300) != run(make(seed=7), 300)


def test_req030_van_moves_along_its_route():
    states = run(make(), 600)
    polyline = fixture_polyline("A")

    assert states[-1].odometer_km > 1.0
    for s in states[::500]:
        assert min(_metres((s.lat, s.lon), p) for p in polyline) < 60


async def test_req030_runner_writes_all_signals_each_tick():
    twin = InMemoryTwin(signals.ALL)
    await run_simulator(make(), twin, FakeClock(), time_scale=1.0, dt_s=DT, ticks=1)

    values = await twin.get(list(signals.STANDARD + (signals.TRIP, signals.SIM_TIME)))

    assert None not in values.values()


@pytest.mark.parametrize("scale", [1.0, 10.0])
async def test_req032_time_scale_divides_wall_time_not_distance(scale):
    twin, clock = InMemoryTwin(signals.ALL), FakeClock()

    await run_simulator(make(), twin, clock, time_scale=scale, dt_s=DT, ticks=1000)

    assert clock.slept_s == pytest.approx(100.0 / scale)
    odometer = (await twin.get([signals.ODOMETER]))[signals.ODOMETER]
    assert odometer == pytest.approx(run(make(), 100)[-1].odometer_km)


async def test_req032_slow_twin_writes_do_not_slow_sim_time():
    clock = FakeClock()

    class SlowTwin(InMemoryTwin):
        async def set(self, values):
            clock.ms += 4  # each databroker write costs 4 ms of wall time
            await super().set(values)

    start = clock.ms
    await run_simulator(make(), SlowTwin(signals.ALL), clock, time_scale=10.0, dt_s=DT, ticks=1000)

    assert clock.ms - start == pytest.approx(10_000, abs=10)  # 100 sim-s at 10x = 10 wall-s
