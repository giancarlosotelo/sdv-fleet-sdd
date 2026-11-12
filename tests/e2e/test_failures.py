import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from contracts import HAZARD_TOPIC, TELEMETRY_TOPIC
from fleet.config import load_config
from fleet.demo.wiring import DemoOptions, build_demo
from tests.harness.routes import fixture_polyline
from tests.harness.server import free_port

pytestmark = pytest.mark.standin
CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
# 2.5 s instead of 10 s keeps this e2e fast but stays clear of the 1 s telemetry period;
# the exact 10 s timing is covered with a fake clock in unit tests.
FAST = replace(CFG, cloud=replace(CFG.cloud, offline_timeout_s=2.5))
ROUTES = {rid: fixture_polyline(rid) for rid in CFG.routes}


@pytest.fixture
async def demo(tmp_path):
    demo = await build_demo(FAST, ROUTES, DemoOptions(port=free_port(), db=tmp_path / "f.db"))
    await demo.start()
    await asyncio.sleep(1.2)
    yield demo
    await demo.stop()


def offline_alerts(demo, vid=None, resolved=None):
    return [
        a
        for a in demo.storage.alerts(include_resolved=True)
        if a.kind == "offline"
        and (vid is None or a.vehicle_id == vid)
        and (resolved is None or (a.resolved_ms is not None) == resolved)
    ]


async def test_req131_malformed_messages_are_quarantined_and_service_keeps_running(demo):
    pubsub = demo.service_pubsub
    for raw in (b"garbage", b'{"kind": "telemetry"}', b"[1, 2]"):
        await pubsub.publish(TELEMETRY_TOPIC, raw)
    await pubsub.publish(HAZARD_TOPIC, b'{"kind": "hazard", "vehicle_id": "veh-99"}')
    before = demo.service.snapshot()["vehicles"]["veh-01"]["odometer_km"]
    await asyncio.sleep(1.5)

    assert demo.service.rejected == 4
    assert len(demo.storage.quarantine()) == 4
    assert demo.service.snapshot()["vehicles"]["veh-01"]["odometer_km"] > before


async def test_req131_silent_van_goes_offline_then_recovers(demo):
    await demo.publishers["veh-03"].stop()
    stopped_ms = demo.clock.now_ms()
    await asyncio.sleep(4.0)

    [alert] = offline_alerts(demo, "veh-03")
    assert 2500 <= alert.opened_ms - stopped_ms <= 3700
    assert demo.service.snapshot()["vehicles"]["veh-03"]["online"] is False
    assert offline_alerts(demo, "veh-01") == []

    demo.publishers["veh-03"].run_in_background()
    await asyncio.sleep(1.5)
    assert offline_alerts(demo, "veh-03", resolved=True)
    assert demo.service.snapshot()["vehicles"]["veh-03"]["online"] is True


@pytest.mark.parametrize("broker", ["zenoh", "pubsub"])
async def test_req131_broker_outage_buffers_then_drains(demo, broker):
    target = demo.vehicle_zenoh if broker == "zenoh" else demo.service_pubsub
    target.up = False
    await asyncio.sleep(4.5)
    during = offline_alerts(demo)
    target.up = True
    outboxes = [p.outbox for p in demo.publishers.values()] + [demo.bridge.outbox]
    for _ in range(100):  # retry backoff tops out at 8 s
        await asyncio.sleep(0.1)
        if all(o.pending == 0 for o in outboxes) and not offline_alerts(demo, resolved=False):
            break

    assert len(during) == 3
    assert all(o.pending == 0 for o in outboxes)
    assert offline_alerts(demo, resolved=False) == []
    assert all(not t.done() for t in demo.tasks)
