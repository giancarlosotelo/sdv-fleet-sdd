from fleet.cloud.offline import OfflineMonitor


def test_req083_silence_beyond_timeout_marks_offline_once():
    monitor = OfflineMonitor(["veh-01", "veh-02"], timeout_s=10.0, now_ms=0)
    monitor.seen("veh-01", 0)
    monitor.seen("veh-02", 5_000)

    assert monitor.check(10_000) == []
    assert monitor.check(10_001) == ["veh-01"]
    assert monitor.check(12_000) == []
    assert monitor.check(15_001) == ["veh-02"]


def test_req083_telemetry_after_offline_reports_back_online():
    monitor = OfflineMonitor(["veh-01"], timeout_s=10.0, now_ms=0)
    monitor.check(10_001)

    assert monitor.seen("veh-01", 11_000) is True
    assert monitor.seen("veh-01", 12_000) is False
    assert monitor.is_online("veh-01")


def test_req083_van_never_heard_from_goes_offline():
    monitor = OfflineMonitor(["veh-03"], timeout_s=10.0, now_ms=1_000)

    assert monitor.check(11_001) == ["veh-03"]
