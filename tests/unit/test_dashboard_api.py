import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fleet.cloud.service import CloudService
from fleet.cloud.storage import SqliteStorage
from fleet.config import load_config
from fleet.dashboard.app import create_app
from tests.harness.clock import FakeClock
from tests.harness.routes import fixture_polyline

CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")
HAZARD = {
    "kind": "hazard",
    "schema_version": 1,
    "msg_id": "00000000-0000-4000-8000-000000000001",
    "vehicle_id": "veh-02",
    "sim_ts": 1.0,
    "wall_ts": 1_000_000,
    "hazard_type": "harsh_braking",
    "severity": 3,
    "t0": 999_900,
    "lat": 43.9,
    "lon": -78.86,
}


@pytest.fixture
def client():
    service = CloudService(CFG, SqliteStorage(":memory:"), FakeClock(start_ms=1_000_000))
    routes = {rid: fixture_polyline(rid) for rid in CFG.routes}
    with TestClient(create_app(service, CFG, routes)) as client:
        client.service = service
        yield client


def test_req110_page_is_served_with_leaflet(client):
    page = client.get("/")

    assert page.status_code == 200
    assert "leaflet" in page.text.lower()


def test_req112_snapshot_has_fleet_latency_and_routes(client):
    snap = client.get("/api/snapshot").json()

    assert sorted(snap["vehicles"]) == ["veh-01", "veh-02", "veh-03"]
    assert snap["latency"]["target_ms"] == 2000
    assert [r["route_id"] for r in snap["route_table"]] == ["A", "B", "C"]
    assert {r["id"] for r in snap["routes"]} == {"A", "B", "C"}


def test_req111_ws_sends_snapshot_then_live_alert(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        client.portal.call(client.service.handle, json.dumps(HAZARD).encode())
        alert = ws.receive_json()
        latency = ws.receive_json()

    assert first["type"] == "snapshot" and len(first["routes"]) == 3
    assert alert["type"] == "alert"
    assert (alert["alert"]["hazard_type"], alert["alert"]["severity"]) == ("harsh_braking", 3)
    assert (alert["alert"]["lat"], alert["alert"]["lon"]) == (43.9, -78.86)
    assert latency["latency"]["max_ms"] == 100


def test_req113_ack_persists_and_reaches_every_client(client):
    client.portal.call(client.service.handle, json.dumps(HAZARD).encode())
    alert_id = client.get("/api/snapshot").json()["alerts"][0]["id"]
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.receive_json(), b.receive_json()
        acked = client.post(f"/api/alerts/{alert_id}/ack")
        pushed = [a.receive_json(), b.receive_json()]

    assert acked.status_code == 200 and acked.json()["acked_ms"] == 1_000_000
    assert [p["alert"]["acked_ms"] for p in pushed] == [1_000_000, 1_000_000]


def test_req113_resolved_alerts_only_on_request(client):
    client.portal.call(client.service.handle, json.dumps(HAZARD).encode())
    cleared = HAZARD | {
        "msg_id": "00000000-0000-4000-8000-000000000002",
        "hazard_type": "none",
        "severity": 0,
    }
    client.portal.call(client.service.handle, json.dumps(cleared).encode())

    assert client.get("/api/snapshot").json()["alerts"] == []
    assert len(client.get("/api/snapshot?include_resolved=true").json()["alerts"]) == 1


def test_req113_ack_unknown_alert_is_404(client):
    assert client.post("/api/alerts/nope/ack").status_code == 404


def test_req114_latency_panel_values_equal_service_stats(client):
    client.portal.call(client.service.handle, json.dumps(HAZARD).encode())

    panel = client.get("/api/snapshot").json()["latency"]
    stats = client.service.latency()

    assert (panel["median_ms"], panel["p95_ms"], panel["max_ms"]) == (
        stats.median_ms,
        stats.p95_ms,
        stats.max_ms,
    )
    assert panel["pass"] is True and panel["target_ms"] == 2000
