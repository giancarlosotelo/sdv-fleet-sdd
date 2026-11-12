from dataclasses import replace

import pytest

from fleet.cloud.storage import Alert, SqliteStorage, Trip

ALERT = Alert(
    id="a1",
    vehicle_id="veh-02",
    kind="hazard",
    hazard_type="harsh_braking",
    severity=3,
    t0_ms=1000,
    t1_ms=1150,
    lat=43.9,
    lon=-78.86,
    opened_ms=1150,
    resolved_ms=None,
    acked_ms=None,
    trip=1,
)
TRIP = Trip(
    vehicle_id="veh-02",
    route_id="B",
    trip=1,
    distance_km=4.3,
    energy_kwh=1.2,
    hazards=3,
    hazards_per_100km=69.8,
    completed_ms=5000,
)
TELEMETRY = {
    "msg_id": "m1",
    "vehicle_id": "veh-01",
    "sim_ts": 1.0,
    "wall_ts": 1000,
    "speed_kmh": 50.0,
}


@pytest.fixture
def db():
    return SqliteStorage(":memory:")


def test_req090_alert_round_trip(db):
    db.save_alert(ALERT)

    assert db.alerts() == [ALERT]


def test_req090_save_alert_upserts_by_id(db):
    db.save_alert(ALERT)
    db.save_alert(replace(ALERT, acked_ms=2000))

    assert db.alerts() == [replace(ALERT, acked_ms=2000)]


def test_req090_alerts_newest_first_and_resolved_hidden_by_default(db):
    older = replace(ALERT, id="old", opened_ms=100)
    resolved = replace(ALERT, id="done", opened_ms=50, resolved_ms=60)
    for alert in (older, ALERT, resolved):
        db.save_alert(alert)

    assert [a.id for a in db.alerts()] == ["a1", "old"]
    assert [a.id for a in db.alerts(include_resolved=True)] == ["a1", "old", "done"]


def test_req090_trip_round_trip_and_filter(db):
    other = replace(TRIP, vehicle_id="veh-01", route_id="A")
    db.add_trip(TRIP)
    db.add_trip(other)

    assert db.trips() == [TRIP, other]
    assert db.trips(vehicle_id="veh-01") == [other]


def test_req090_telemetry_and_quarantine_round_trip(db):
    db.add_telemetry(TELEMETRY, vehicle_name="Van 01", route_id="A")
    db.add_quarantine(b"not json", "<root>: not json", received_ms=7)

    assert db.telemetry() == [{**TELEMETRY, "vehicle_name": "Van 01", "route_id": "A"}]
    assert db.quarantine() == [(b"not json", "<root>: not json", 7)]


def test_req086_data_survives_reopen(tmp_path):
    path = tmp_path / "fleet.db"
    first = SqliteStorage(path)
    first.save_alert(ALERT)
    first.add_trip(TRIP)
    first.close()

    reopened = SqliteStorage(path)

    assert reopened.alerts() == [ALERT]
    assert reopened.trips() == [TRIP]
