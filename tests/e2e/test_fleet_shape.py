import asyncio
import random
from pathlib import Path

import httpx
import pytest

from fleet.cloud.service import CloudService
from fleet.cloud.storage import SqliteStorage
from fleet.config import load_config
from fleet.demo.wiring import DemoOptions, build_demo
from fleet.transport.bridge import Bridge
from fleet.transport.pubsub import StandInPubSub
from fleet.transport.zenoh import StandInZenoh
from fleet.vehicle import signals
from fleet.vehicle.detector import Detector
from fleet.vehicle.publisher import Publisher
from fleet.vehicle.simulator import Simulator, state_to_signals
from fleet.vehicle.twin import InMemoryTwin
from tests.harness.clock import FakeClock
from tests.harness.routes import fixture_polyline
from tests.harness.server import free_port

pytestmark = pytest.mark.standin
ROOT = Path(__file__).resolve().parents[2]
CFG = load_config(ROOT / "config" / "fleet.yaml")
DT, TIME_SCALE = 0.1, 10.0


async def test_req033_route_b_has_most_hazards_per_100km_after_first_trips():
    clock, zenoh, pubsub = FakeClock(), StandInZenoh(), StandInPubSub()
    service = CloudService(CFG, SqliteStorage(":memory:"), clock)
    await service.start(pubsub)
    await Bridge(zenoh, pubsub, clock, buffer_size=60).start()
    vans = []
    for van in CFG.vehicles:
        twin = InMemoryTwin(signals.ALL)
        await Detector(twin, van.route.speed_limit_kmh, CFG.thresholds, clock).start()
        pub = Publisher(van.id, twin, zenoh, clock, telemetry_hz=1.0, buffer_size=60)
        await pub.start()
        sim = Simulator(
            van, fixture_polyline(van.route.id), CFG.charging, random.Random(f"42-{van.id}")
        )
        vans.append((sim, twin, pub))
    ticks_per_telemetry = round(TIME_SCALE / DT)  # 1 Hz wall at this time scale

    tick = 0
    while not all(r["trips"] >= 1 for r in service.route_table()):
        for sim, twin, pub in vans:
            await twin.set(state_to_signals(sim.step(DT)))
            if tick % ticks_per_telemetry == 0:
                await pub.run_telemetry(ticks=1)
        clock.ms += round(DT / TIME_SCALE * 1000)
        tick += 1
        assert tick < 200_000, "vans never completed a trip"

    rows = {r["route_id"]: r for r in service.route_table()}
    assert rows["B"]["highest"], rows
    assert rows["B"]["hazards_per_100km"] > max(
        rows["A"]["hazards_per_100km"], rows["C"]["hazards_per_100km"]
    )


async def test_req001_extra_config_entry_adds_a_van(tmp_path):
    cfg = load_config(ROOT / "tests" / "fixtures" / "fleet-4vans.yaml")
    routes = {rid: fixture_polyline(rid) for rid in cfg.routes}
    port = free_port()
    demo = await build_demo(cfg, routes, DemoOptions(port=port, db=tmp_path / "f.db"))
    await demo.start()
    try:
        await asyncio.sleep(1.5)
        async with httpx.AsyncClient() as http:
            snapshot = (await http.get(f"http://127.0.0.1:{port}/api/snapshot")).json()
    finally:
        await demo.stop()

    assert snapshot["vehicles"]["veh-04"]["speed_kmh"] is not None
    assert snapshot["vehicles"]["veh-04"]["route_id"] == "B"
