import pytest

from fleet.cloud.trips import TripTracker


def tel(trip, odo, soc, vid="veh-02"):
    return {"vehicle_id": vid, "trip": trip, "odometer_km": odo, "soc_pct": soc}


@pytest.fixture
def tracker():
    return TripTracker(pack_kwh={"veh-02": 68.0}, route={"veh-02": "B"})


def test_req085_completed_trip_records_distance_energy_hazards(tracker):
    tracker.telemetry(tel(1, 0.0, 60.0), now_ms=0)
    tracker.telemetry(tel(1, 2.0, 59.0), now_ms=1)
    tracker.hazard_opened("veh-02")
    tracker.hazard_opened("veh-02")

    trip = tracker.telemetry(tel(2, 4.3, 58.0), now_ms=99)

    assert (trip.vehicle_id, trip.route_id, trip.trip, trip.hazards, trip.completed_ms) == (
        "veh-02",
        "B",
        1,
        2,
        99,
    )
    assert trip.distance_km == pytest.approx(4.3)
    assert trip.energy_kwh == pytest.approx(1.36)
    assert trip.hazards_per_100km == pytest.approx(2 / 4.3 * 100)


def test_req085_charging_rise_is_not_negative_energy(tracker):
    tracker.telemetry(tel(1, 0.0, 12.0), now_ms=0)
    tracker.telemetry(tel(2, 4.3, 10.0), now_ms=1)
    tracker.telemetry(tel(2, 4.3, 90.0), now_ms=2)

    trip = tracker.telemetry(tel(3, 8.6, 88.0), now_ms=3)

    assert trip.energy_kwh == pytest.approx(0.02 * 68.0)


def test_req085_partial_first_trip_is_not_recorded(tracker):
    tracker.telemetry(tel(3, 11.0, 50.0), now_ms=0)

    assert tracker.telemetry(tel(4, 12.9, 49.0), now_ms=1) is None
    assert tracker.telemetry(tel(5, 17.2, 47.0), now_ms=2).trip == 4


def test_req085_hazards_counted_on_the_trip_they_opened_in(tracker):
    tracker.telemetry(tel(1, 0.0, 60.0), now_ms=0)
    tracker.hazard_opened("veh-02")
    tracker.telemetry(tel(2, 4.3, 59.0), now_ms=1)

    assert tracker.telemetry(tel(3, 8.6, 58.0), now_ms=2).hazards == 0
