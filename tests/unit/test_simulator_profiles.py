import itertools
import random
from dataclasses import replace
from pathlib import Path

import pytest

from fleet.config import load_config
from fleet.vehicle.simulator import Simulator
from tests.harness.routes import fixture_polyline

CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
VAN = {v.id: v for v in CFG.vehicles}
DT = 0.5


def make(vid, **van_changes) -> Simulator:
    van = replace(VAN[vid], **van_changes)
    return Simulator(van, fixture_polyline(van.route.id), CFG.charging, random.Random(f"42-{vid}"))


def run_km(sim: Simulator, km: float):
    states = [sim.step(DT)]
    while states[-1].odometer_km < km:
        states.append(sim.step(DT))
    return states


def test_req035_trip_increments_once_per_loop():
    sim = make("veh-02")
    states = run_km(sim, 3 * sim.loop_km + 0.1)

    changes = [s.odometer_km for a, s in itertools.pairwise(states) if s.trip != a.trip]

    assert [b.trip for b in states][-1] == 4
    assert changes == pytest.approx([sim.loop_km, 2 * sim.loop_km, 3 * sim.loop_km], abs=0.05)


def test_req035_odometer_never_decreases():
    states = run_km(make("veh-01"), 25)

    assert all(b.odometer_km >= a.odometer_km for a, b in itertools.pairwise(states))


def test_req034_long_run_crosses_both_low_energy_thresholds_and_charges():
    states = run_km(make("veh-03", start_soc_pct=25.0), 120)
    socs = [s.soc_pct for s in states]

    assert min(socs) <= 10.0
    assert socs[0] > 20.0
    assert max(socs[socs.index(min(socs)) :]) == pytest.approx(90.0, abs=0.5)


def test_req036_soc_rises_only_while_stopped_at_route_start():
    sim = make("veh-02", start_soc_pct=12.0)
    states = run_km(sim, 20)
    start = fixture_polyline("B")[0]

    rising = [b for a, b in itertools.pairwise(states) if b.soc_pct > a.soc_pct]

    assert rising
    assert all(s.speed_kmh == 0 and (s.lat, s.lon) == pytest.approx(start) for s in rising)


def test_req036_trip_after_charging_starts_at_route_start():
    sim = make("veh-02", start_soc_pct=12.0)
    states = run_km(sim, 20)
    charge_end = max(
        i for i, (a, b) in enumerate(itertools.pairwise(states)) if b.soc_pct > a.soc_pct
    )

    after = states[charge_end + 1]

    assert (after.lat, after.lon) == pytest.approx(fixture_polyline("B")[0])


def _harsh_brakes_per_km(vid: str) -> float:
    states = run_km(make(vid), 40)
    onsets = sum(1 for a, b in itertools.pairwise(states) if b.accel_ms2 <= -4.0 < a.accel_ms2)
    return onsets / states[-1].odometer_km


def test_req033_downtown_profile_brakes_hardest():
    b = _harsh_brakes_per_km("veh-02")

    assert b > 1.5 * _harsh_brakes_per_km("veh-01")
    assert b > 1.5 * _harsh_brakes_per_km("veh-03")
