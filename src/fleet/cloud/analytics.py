import itertools
import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyStats:
    count: int
    median_ms: float | None
    p95_ms: float | None
    max_ms: float | None


def latency_stats(latencies_ms: list[float]) -> LatencyStats:
    """p95 is nearest-rank: the ceil(0.95 * n)-th smallest value."""
    if not latencies_ms:
        return LatencyStats(0, None, None, None)
    ordered = sorted(latencies_ms)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return LatencyStats(len(ordered), statistics.median(ordered), p95, ordered[-1])


def energy_used_kwh(soc_series_pct: list[float], pack_kwh: float) -> float:
    drops = sum(max(a - b, 0.0) for a, b in itertools.pairwise(soc_series_pct))
    return drops / 100 * pack_kwh


def hazards_per_100km(hazards: int, distance_km: float) -> float | None:
    return None if distance_km <= 0 else hazards / distance_km * 100
