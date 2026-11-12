import itertools
import json
from pathlib import Path

import pytest

from contracts import HAZARD_TOPIC, TELEMETRY_TOPIC
from fleet.cloud.service import CloudService
from fleet.cloud.storage import SqliteStorage
from fleet.config import load_config
from fleet.transport.pubsub import StandInPubSub
from tests.harness.clock import FakeClock

pytestmark = pytest.mark.standin
CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
_ids = itertools.count()


def telemetry(vid, trip, odo, soc, wall_ts=0):
    return {
        "kind": "telemetry",
        "schema_version": 1,
        "msg_id": f"00000000-0000-4000-8000-{next(_ids):012d}",
        "vehicle_id": vid,
        "sim_ts": 1.0,
        "wall_ts": wall_ts,
        "lat": 43.9,
        "lon": -78.86,
        "speed_kmh": 40.0,
        "accel_ms2": 0.0,
        "traction_active": False,
        "soc_pct": soc,
        "coolant_c": 70.0,
        "odometer_km": odo,
        "trip": trip,
    }


def hazard(vid, kind, severity, t0):
    return {
        "kind": "hazard",
        "schema_version": 1,
        "msg_id": f"00000000-0000-4000-8000-{next(_ids):012d}",
        "vehicle_id": vid,
        "sim_ts": 1.0,
        "wall_ts": t0,
        "hazard_type": kind,
        "severity": severity,
        "t0": t0,
        "lat": 43.9,
        "lon": -78.86,
    }


@pytest.fixture
async def env(tmp_path):
    clock, pubsub = FakeClock(start_ms=1_000_000), StandInPubSub()
    storage = SqliteStorage(tmp_path / "fleet.db")
    service = CloudService(CFG, storage, clock)
    await service.start(pubsub)
    events = []

    async def listen(event):
        events.append(event)

    service.listen(listen)

    async def send(topic, msg):
        await pubsub.publish(topic, json.dumps(msg).encode())

    return service, storage, clock, send, events


async def test_req084_latency_is_receipt_minus_t0(env):
    service, storage, clock, send, events = env
    await send(HAZARD_TOPIC, hazard("veh-02", "harsh_braking", 3, t0=clock.ms - 150))
    await send(HAZARD_TOPIC, hazard("veh-01", "overspeed", 1, t0=clock.ms - 450))

    stats = service.latency()

    assert (stats.count, stats.median_ms, stats.max_ms) == (2, 300, 450)
    assert [a.t1_ms - a.t0_ms for a in storage.alerts()] == [450, 150]


async def test_req085_trip_recorded_with_hazards_on_trip_change(env):
    service, storage, clock, send, events = env
    await send(TELEMETRY_TOPIC, telemetry("veh-02", 1, 0.0, 60.0))
    await send(HAZARD_TOPIC, hazard("veh-02", "harsh_braking", 3, t0=clock.ms))
    await send(TELEMETRY_TOPIC, telemetry("veh-02", 2, 4.3, 59.0))

    [trip] = storage.trips()

    assert (trip.vehicle_id, trip.route_id, trip.trip, trip.hazards) == ("veh-02", "B", 1, 1)
    assert storage.alerts()[0].trip == 1
    assert any(e["type"] == "route_table" for e in events)


async def test_req080_malformed_is_dropped_service_keeps_running(env):
    service, storage, clock, send, events = env
    await service.handle(b"not json")
    await send(TELEMETRY_TOPIC, telemetry("veh-01", 1, 0.0, 60.0))

    assert service.rejected == 1
    assert service.snapshot()["vehicles"]["veh-01"]["soc_pct"] == 60.0


async def test_req083_offline_alert_opens_and_resolves(env):
    service, storage, clock, send, events = env
    await send(TELEMETRY_TOPIC, telemetry("veh-01", 1, 0.0, 60.0))
    clock.ms += 10_500

    await service.check_offline()
    offline = [a for a in storage.alerts() if a.kind == "offline"]
    assert sorted(a.vehicle_id for a in offline) == ["veh-01", "veh-02", "veh-03"]

    await send(TELEMETRY_TOPIC, telemetry("veh-01", 1, 0.1, 60.0))
    assert sorted(a.vehicle_id for a in storage.alerts() if a.kind == "offline") == [
        "veh-02",
        "veh-03",
    ]
    assert service.snapshot()["vehicles"]["veh-01"]["online"] is True


async def test_req082_ack_persists_and_is_broadcast(env):
    service, storage, clock, send, events = env
    await send(HAZARD_TOPIC, hazard("veh-02", "overheat", 2, t0=clock.ms))
    alert_id = storage.alerts()[0].id
    clock.ms += 5000

    await service.ack(alert_id)
    await service.ack(alert_id)

    assert storage.alerts()[0].acked_ms == 1_005_000
    assert events[-1]["type"] == "alert" and events[-1]["alert"]["acked_ms"] == 1_005_000


async def test_req086_restart_keeps_alerts_and_resolves_open_ones(env, tmp_path):
    service, storage, clock, send, events = env
    await send(HAZARD_TOPIC, hazard("veh-02", "overheat", 2, t0=clock.ms))
    await service.ack(storage.alerts()[0].id)
    storage.close()

    pubsub = StandInPubSub()
    restarted = CloudService(CFG, SqliteStorage(tmp_path / "fleet.db"), clock)
    await restarted.start(pubsub)
    assert restarted.snapshot()["alerts"][0]["acked_ms"] is not None

    await pubsub.publish(
        HAZARD_TOPIC, json.dumps(hazard("veh-02", "none", 0, t0=clock.ms)).encode()
    )
    assert restarted.snapshot()["alerts"] == []


async def test_req115_route_table_aggregates_completed_trips(env):
    from fleet.cloud.storage import Trip

    service, storage, clock, send, events = env
    for trip, km, kwh, hazards in [(1, 4.0, 1.0, 2), (2, 6.0, 1.5, 4)]:
        storage.add_trip(Trip("veh-02", "B", trip, km, kwh, hazards, hazards / km * 100, 0))
    storage.add_trip(Trip("veh-01", "A", 1, 10.0, 2.5, 1, 10.0, 0))

    rows = {r["route_id"]: r for r in service.route_table()}

    assert (rows["B"]["trips"], rows["B"]["km"], rows["B"]["kwh"], rows["B"]["hazards"]) == (
        2,
        10.0,
        2.5,
        6,
    )
    assert rows["B"]["hazards_per_100km"] == pytest.approx(60.0)
    assert rows["B"]["kwh_per_100km"] == pytest.approx(25.0)
    assert rows["B"]["highest"] and not rows["A"]["highest"]
    assert (rows["C"]["trips"], rows["C"]["km"], rows["C"]["hazards_per_100km"]) == (0, None, None)
