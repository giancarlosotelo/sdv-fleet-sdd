from types import SimpleNamespace

from fleet.cloud.storage import Alert, SqliteStorage
from fleet.demo.report import latency_report


def _alert(i, latency_ms, opened_ms=1_000, kind="harsh_braking", severity=3):
    return Alert(
        f"a{i}",
        "veh-01",
        "hazard",
        kind,
        severity,
        opened_ms - latency_ms,
        opened_ms,
        0.0,
        0.0,
        opened_ms,
        None,
        None,
        1,
    )


def _demo(alerts):
    storage = SqliteStorage(":memory:")
    for alert in alerts:
        storage.save_alert(alert)
    return SimpleNamespace(storage=storage)


def test_req121_report_passes_when_all_injected_arrive_fast():
    demo = _demo(
        [_alert(i, 100 + i) for i in range(10)] + [_alert(99, 5, kind="overspeed", severity=1)]
    )

    report = latency_report(demo, since_ms=0, expected=10)

    assert report.passed and report.injected_alerts == 10 and report.stats.count == 11
    assert "PASS" in report.text and "median" in report.text and "p95" in report.text


def test_req121_report_fails_on_slow_p95_or_missing_alerts():
    slow = latency_report(_demo([_alert(i, 2500) for i in range(5)]), since_ms=0, expected=5)
    missing = latency_report(_demo([_alert(i, 10) for i in range(3)]), since_ms=0, expected=5)

    assert not slow.passed and "FAIL" in slow.text
    assert not missing.passed


def test_req121_report_ignores_alerts_before_injection_started():
    report = latency_report(
        _demo([_alert(1, 5000, opened_ms=10), _alert(2, 10, opened_ms=2_000)]),
        since_ms=1_000,
        expected=1,
    )

    assert report.stats.count == 1 and report.passed
