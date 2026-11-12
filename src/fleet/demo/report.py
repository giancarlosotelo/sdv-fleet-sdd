from dataclasses import dataclass

from fleet.cloud.analytics import LatencyStats, latency_stats
from fleet.cloud.service import LATENCY_TARGET_MS
from fleet.demo.wiring import Demo


@dataclass(frozen=True)
class LatencyReport:
    stats: LatencyStats
    injected_alerts: int
    expected: int
    passed: bool
    text: str


def latency_report(demo: Demo, since_ms: int, expected: int) -> LatencyReport:
    alerts = [
        a
        for a in demo.storage.alerts(include_resolved=True)
        if a.kind == "hazard" and a.opened_ms >= since_ms
    ]
    stats = latency_stats([a.t1_ms - a.t0_ms for a in alerts])
    injected = sum(1 for a in alerts if a.hazard_type == "harsh_braking" and a.severity == 3)
    passed = injected >= expected and stats.p95_ms is not None and stats.p95_ms < LATENCY_TARGET_MS
    text = (
        f"hazard alerts: {stats.count} (injected harsh braking: {injected}/{expected})\n"
        f"latency ms: median {stats.median_ms}  p95 {stats.p95_ms}  max {stats.max_ms}\n"
        f"target p95 < {LATENCY_TARGET_MS} ms: {'PASS' if passed else 'FAIL'}"
    )
    return LatencyReport(stats, injected, expected, passed, text)
