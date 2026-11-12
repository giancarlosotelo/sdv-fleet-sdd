from types import SimpleNamespace

from fleet.cloud.storage import Alert, SqliteStorage
from fleet.demo.inject import Injection
from fleet.demo.report import latency_report


def _alert(i, t0, latency_ms, vid="veh-01", kind="harsh_braking", severity=3):
    return Alert(
        f"a{i}",
        vid,
        "hazard",
        kind,
        severity,
        t0,
        t0 + latency_ms,
        0.0,
        0.0,
        t0 + latency_ms,
        None,
        None,
        1,
    )


def _demo(alerts):
    storage = SqliteStorage(":memory:")
    for alert in alerts:
        storage.save_alert(alert)
    return SimpleNamespace(storage=storage)


INJECTIONS = [Injection("veh-01", 1_000 * i) for i in range(1, 6)]


def test_req121_report_passes_when_every_injection_arrives_fast():
    demo = _demo([_alert(i, inj.at_ms + 2, 100 + i) for i, inj in enumerate(INJECTIONS)])

    report = latency_report(demo, INJECTIONS)

    assert report.passed and report.injected_alerts == 5 and report.stats.count == 5
    assert "PASS" in report.text and "median" in report.text and "p95" in report.text


def test_req121_natural_harsh_brakes_do_not_count_as_injections():
    """The simulator brakes at up to 8 m/s^2 itself; those must not top up lost injections."""
    arrived = [_alert(i, inj.at_ms + 2, 50) for i, inj in enumerate(INJECTIONS[:3])]
    natural = [_alert(10 + i, 50_000 + i * 700, 50) for i in range(3)]
    other_van = [_alert(20, INJECTIONS[3].at_ms + 2, 50, vid="veh-02")]

    report = latency_report(_demo(arrived + natural + other_van), INJECTIONS)

    assert report.injected_alerts == 3
    assert not report.passed and "FAIL" in report.text


def test_req121_slow_injected_alerts_fail():
    demo = _demo([_alert(i, inj.at_ms + 2, 2500) for i, inj in enumerate(INJECTIONS)])

    assert not latency_report(demo, INJECTIONS).passed
