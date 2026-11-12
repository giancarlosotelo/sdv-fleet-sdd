import pytest

from fleet.cloud.analytics import LatencyStats, energy_used_kwh, hazards_per_100km, latency_stats


def test_req084_stats_on_known_latencies():
    latencies = [100 * i for i in range(1, 21)]  # 100..2000 ms

    # median of 20 = mean of 10th and 11th; nearest-rank p95 = ceil(0.95 * 20) = 19th value
    assert latency_stats(latencies) == LatencyStats(
        count=20, median_ms=1050, p95_ms=1900, max_ms=2000
    )


def test_req084_stats_are_order_independent_and_single_value_safe():
    assert latency_stats([300, 100, 200]) == LatencyStats(3, 200, 300, 300)
    assert latency_stats([5]) == LatencyStats(1, 5, 5, 5)


def test_req084_no_latencies_gives_empty_stats():
    assert latency_stats([]) == LatencyStats(0, None, None, None)


def test_req085_energy_counts_soc_decreases_only():
    # drops of 2 and 4 points; the 1-point rise is charging, not negative use
    assert energy_used_kwh([60.0, 58.0, 59.0, 55.0], pack_kwh=68.0) == pytest.approx(4.08)


def test_req085_hazards_per_100km():
    assert hazards_per_100km(3, 4.3) == pytest.approx(69.767, rel=1e-3)


def test_req085_zero_distance_gives_none():
    assert hazards_per_100km(2, 0.0) is None
