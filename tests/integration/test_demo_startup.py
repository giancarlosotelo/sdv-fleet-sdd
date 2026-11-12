import asyncio
from pathlib import Path

import httpx
import pytest

from fleet.config import load_config
from fleet.demo.wiring import DemoOptions, build_demo
from tests.harness.routes import fixture_polyline
from tests.harness.server import free_port

pytestmark = pytest.mark.standin
CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
ROUTES = {rid: fixture_polyline(rid) for rid in CFG.routes}


async def test_req120_demo_starts_serves_dashboard_and_vans_report(tmp_path):
    port = free_port()
    demo = await build_demo(
        CFG, ROUTES, DemoOptions(port=port, time_scale=10.0, seed=42, db=tmp_path / "f.db")
    )
    await demo.start()
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http:
            for _ in range(100):
                try:
                    page = await http.get("/")
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
            await asyncio.sleep(1.5)
            snapshot = (await http.get("/api/snapshot")).json()
    finally:
        await demo.stop()

    assert page.status_code == 200
    assert all(v["speed_kmh"] is not None for v in snapshot["vehicles"].values())


async def test_req120_capture_writes_received_messages(tmp_path):
    capture = tmp_path / "capture.jsonl"
    demo = await build_demo(
        CFG, ROUTES, DemoOptions(port=free_port(), db=tmp_path / "f.db", capture=capture)
    )
    await demo.start()
    await asyncio.sleep(1.5)
    await demo.stop()

    lines = capture.read_text().splitlines()
    assert len(lines) >= 3 and '"received_ms"' in lines[0]
