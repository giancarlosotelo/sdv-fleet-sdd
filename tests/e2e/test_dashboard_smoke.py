import asyncio
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from fleet.cloud.service import CloudService
from fleet.cloud.storage import SqliteStorage
from fleet.config import load_config
from fleet.dashboard.app import create_app
from tests.harness.clock import FakeClock
from tests.harness.routes import fixture_polyline
from tests.harness.server import ServerThread

pytestmark = pytest.mark.standin
CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")


def telemetry(i, van):
    lat, lon = fixture_polyline(van.route.id)[0]
    return {
        "kind": "telemetry",
        "schema_version": 1,
        "msg_id": f"00000000-0000-4000-8000-00000000000{i}",
        "vehicle_id": van.id,
        "sim_ts": 1.0,
        "wall_ts": 1,
        "lat": lat,
        "lon": lon,
        "speed_kmh": 30.0,
        "accel_ms2": 0.0,
        "traction_active": False,
        "soc_pct": 60.0,
        "coolant_c": 70.0,
        "odometer_km": 0.0,
        "trip": 1,
    }


def test_req111_map_renders_routes_and_vans_without_tiles():
    service = CloudService(CFG, SqliteStorage(":memory:"), FakeClock())
    for i, van in enumerate(CFG.vehicles):
        asyncio.run(service.handle(json.dumps(telemetry(i, van)).encode()))
    hazard = {
        "kind": "hazard",
        "schema_version": 1,
        "msg_id": "00000000-0000-4000-8000-000000000099",
        "vehicle_id": "veh-02",
        "sim_ts": 1.0,
        "wall_ts": 1,
        "hazard_type": "harsh_braking",
        "severity": 3,
        "t0": 1,
        "lat": 43.8975,
        "lon": -78.8636,
    }
    asyncio.run(service.handle(json.dumps(hazard).encode()))
    resolved_earlier = hazard | {
        "msg_id": "00000000-0000-4000-8000-000000000098",
        "vehicle_id": "veh-01",
        "hazard_type": "overspeed",
        "severity": 1,
        "lat": 43.93,
        "lon": -78.87,
    }
    cleared = resolved_earlier | {
        "msg_id": "00000000-0000-4000-8000-000000000097",
        "hazard_type": "none",
        "severity": 0,
    }
    for msg in (resolved_earlier, cleared):
        asyncio.run(service.handle(json.dumps(msg).encode()))
    app = create_app(service, CFG, {rid: fixture_polyline(rid) for rid in CFG.routes})

    with ServerThread(app) as url, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        blocked = []
        page.route(
            "**/*",
            lambda r: (
                (blocked.append(r.request.url), r.abort())
                if "127.0.0.1" not in r.request.url
                else r.continue_()
            ),
        )
        page.goto(url)
        page.wait_for_selector("path.van", state="attached")

        assert page.locator("path.route").count() == 3
        assert page.locator("path.van").count() == 3
        assert page.locator("path.hazard-dot.sev-dot-3").count() == 1
        assert page.locator("path.van-pulse").count() == 1
        assert page.locator("#fleet tbody tr").count() == 3
        page.wait_for_selector("path.hazard-dot.sev-dot-1", state="attached")
        assert page.locator("path.hazard-dot").count() == 2
        assert page.locator("#alerts li[data-alert]").count() == 1
        page.check("#show-resolved")
        assert page.locator("#alerts li[data-alert]").count() == 2
        assert any("tile.openstreetmap.org" in u for u in blocked)
        browser.close()
