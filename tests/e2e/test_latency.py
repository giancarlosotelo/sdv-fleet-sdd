import asyncio
import json
from pathlib import Path

import pytest
import websockets

from fleet.config import load_config
from fleet.demo.inject import inject_hazards
from fleet.demo.report import latency_report
from fleet.demo.wiring import DemoOptions, build_demo
from tests.harness.real import require_service
from tests.harness.routes import fixture_polyline
from tests.harness.server import free_port

CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
ROUTES = {rid: fixture_polyline(rid) for rid in CFG.routes}
N = 20


def nearest_rank_p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[-(-95 * len(ordered) // 100) - 1]


@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("standin", marks=pytest.mark.standin),
        pytest.param("real", marks=pytest.mark.real),
    ],
)
async def test_req130_hard_brake_to_cloud_and_dashboard_under_2s(tmp_path, mode):
    real = mode == "real"
    if real:
        for i in range(len(CFG.vehicles)):
            require_service(f"kuksa databroker {i + 1}", 55561 + i)
        require_service("zenoh router", 7447)
        require_service("pubsub emulator", 8085)
    port = free_port()
    opts = DemoOptions(
        port=port,
        time_scale=10.0,
        db=tmp_path / "f.db",
        real_kuksa=real,
        real_zenoh=real,
        real_pubsub=real,
    )
    demo = await build_demo(CFG, ROUTES, opts)
    await demo.start()
    client_latencies = []
    try:
        await asyncio.sleep(3.0 if real else 1.0)
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
            await ws.recv()

            async def watch():
                while True:
                    event = json.loads(await ws.recv())
                    alert = event.get("alert", {})
                    if alert.get("kind") == "hazard" and alert["resolved_ms"] is None:
                        client_latencies.append(demo.clock.now_ms() - alert["t0_ms"])

            watcher = asyncio.create_task(watch())
            started_ms = demo.clock.now_ms()
            injected = await inject_hazards(demo, N)
            await asyncio.sleep(1.0)
            watcher.cancel()
        report = latency_report(demo, since_ms=started_ms, expected=injected)
    finally:
        await demo.stop()

    print(f"\n[{mode}] {report.text}\nclient p95 {nearest_rank_p95(client_latencies)} ms")
    assert injected == N
    assert report.passed, report.text
    assert nearest_rank_p95(client_latencies) < 2000
