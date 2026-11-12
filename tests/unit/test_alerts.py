import itertools

import pytest

from fleet.cloud.alerts import AlertBook


def hazard(kind, severity, t0, vid="veh-02"):
    return {
        "vehicle_id": vid,
        "hazard_type": kind,
        "severity": severity,
        "t0": t0,
        "lat": 43.9,
        "lon": -78.86,
    }


@pytest.fixture
def book():
    ids = (f"a{i}" for i in itertools.count(1))
    return AlertBook(new_id=lambda: next(ids))


def test_req081_escalation_opens_new_alert_and_clear_resolves_all(book):
    changes = []
    changes += book.hazard(hazard("harsh_braking", 2, t0=1000), t1_ms=1100, trip=1)
    changes += book.hazard(hazard("harsh_braking", 3, t0=1200), t1_ms=1300, trip=1)
    changes += book.hazard(hazard("none", 0, t0=1500), t1_ms=1600, trip=1)

    final = {a.id: a for a in changes}
    assert sorted(final) == ["a1", "a2"]
    assert (final["a1"].severity, final["a1"].resolved_ms) == (2, 1300)
    assert (final["a2"].severity, final["a2"].resolved_ms) == (3, 1600)
    assert book.open_hazards() == []


def test_req081_alert_keeps_its_opening_t0_and_position(book):
    [opened] = book.hazard(hazard("overheat", 2, t0=1000), t1_ms=1100, trip=4)

    assert (opened.t0_ms, opened.t1_ms, opened.lat, opened.trip) == (1000, 1100, 43.9, 4)


def test_req081_same_hazard_again_is_a_no_op(book):
    book.hazard(hazard("overheat", 2, t0=1000), t1_ms=1100, trip=1)

    assert book.hazard(hazard("overheat", 2, t0=1000), t1_ms=1200, trip=1) == []


def test_req081_clear_without_open_alert_is_a_no_op(book):
    assert book.hazard(hazard("none", 0, t0=1000), t1_ms=1100, trip=1) == []


def test_req082_ack_keeps_first_time_and_does_not_resolve(book):
    [opened] = book.hazard(hazard("overspeed", 1, t0=1000), t1_ms=1100, trip=1)

    acked = book.ack(opened, now_ms=2000)
    again = book.ack(acked, now_ms=3000)

    assert (again.acked_ms, again.resolved_ms) == (2000, None)


def test_req083_offline_opens_and_online_resolves(book):
    opened = book.offline("veh-01", now_ms=10_000)
    resolved = book.online("veh-01", now_ms=15_000)

    assert (opened.kind, opened.t0_ms, opened.resolved_ms) == ("offline", None, None)
    assert (resolved.id, resolved.resolved_ms) == (opened.id, 15_000)
    assert book.online("veh-01", now_ms=16_000) is None


def test_req086_book_restores_open_alerts(book):
    [opened] = book.hazard(hazard("overheat", 2, t0=1000), t1_ms=1100, trip=1)
    restored = AlertBook(new_id=lambda: "x", open_alerts=[opened])

    [resolved] = restored.hazard(hazard("none", 0, t0=2000), t1_ms=2100, trip=1)

    assert (resolved.id, resolved.resolved_ms) == (opened.id, 2100)


def test_req081_stale_hazard_after_newer_clear_is_ignored(book):
    """Pub/Sub has no ordering guarantee: an older message must not reopen an alert."""
    assert book.hazard(hazard("none", 0, t0=1050), t1_ms=1100, trip=1) == []

    assert book.hazard(hazard("harsh_braking", 3, t0=900), t1_ms=1200, trip=1) == []
    assert book.open_hazards() == []


def test_req081_stale_resend_does_not_resolve_newer_alert(book):
    book.hazard(hazard("overheat", 2, t0=2000), t1_ms=2100, trip=1)

    assert book.hazard(hazard("none", 0, t0=1500), t1_ms=2200, trip=1) == []
    assert [a.t0_ms for a in book.open_hazards()] == [2000]


def test_req081_same_hazard_with_newer_t0_reopens(book):
    """Outbox keeps only the latest hazard, so high -> none -> high can arrive as high, high."""
    [first] = book.hazard(hazard("harsh_braking", 2, t0=1000), t1_ms=1100, trip=1)

    changed = book.hazard(hazard("harsh_braking", 2, t0=5000), t1_ms=5100, trip=1)

    assert [(a.id, a.resolved_ms) for a in changed] == [(first.id, 5100), ("a2", None)]
    assert changed[1].t0_ms == 5000


def test_req082_ack_survives_later_resolve(book):
    [opened] = book.hazard(hazard("overheat", 2, t0=1000), t1_ms=1100, trip=1)
    book.ack(opened, now_ms=1500)

    [resolved] = book.hazard(hazard("none", 0, t0=2000), t1_ms=2100, trip=1)

    assert (resolved.acked_ms, resolved.resolved_ms) == (1500, 2100)


def test_req081_two_changes_in_the_same_millisecond_both_apply(book):
    book.hazard(hazard("harsh_braking", 2, t0=1000), t1_ms=1100, trip=1)

    changed = book.hazard(hazard("harsh_braking", 3, t0=1000), t1_ms=1101, trip=1)

    assert [a.severity for a in book.open_hazards()] == [3]
    assert len(changed) == 2
