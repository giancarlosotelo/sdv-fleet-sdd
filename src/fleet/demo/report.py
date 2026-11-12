from dataclasses import dataclass

from fleet.cloud.analytics import LatencyStats, latency_stats
from fleet.cloud.service import LATENCY_TARGET_MS
from fleet.cloud.storage import Alert
from fleet.demo.inject import Injection
from fleet.demo.wiring import Demo

# The detector stamps t0 right after the injected write; a natural brake on the same van
# within this window is the only thing that could be mistaken for an injection.
MATCH_WINDOW_MS = 250


@dataclass(frozen=True)
class LatencyReport:
    stats: LatencyStats
    injected_alerts: int
    expected: int
    passed: bool
    text: str


def _match(injections: list[Injection], alerts: list[Alert]) -> list[Alert]:
    """Pairs each injection with the critical harsh-braking alert it caused, at most one each."""
    candidates = sorted(
        (a for a in alerts if a.hazard_type == "harsh_braking" and a.severity == 3),
        key=lambda a: a.t0_ms,
    )
    matched, used = [], set()
    for inj in injections:
        hit = next(
            (
                a
                for a in candidates
                if a.id not in used
                and a.vehicle_id == inj.vehicle_id
                and 0 <= a.t0_ms - inj.at_ms < MATCH_WINDOW_MS
            ),
            None,
        )
        if hit:
            used.add(hit.id)
            matched.append(hit)
    return matched


def latency_report(demo: Demo, injections: list[Injection]) -> LatencyReport:
    matched = _match(injections, demo.storage.alerts(include_resolved=True))
    stats = latency_stats([a.t1_ms - a.t0_ms for a in matched])
    expected = len(injections)
    passed = (
        len(matched) == expected and stats.p95_ms is not None and stats.p95_ms < LATENCY_TARGET_MS
    )
    text = (
        f"injected hazards: {expected}, alerts received: {len(matched)}\n"
        f"latency ms: median {stats.median_ms}  p95 {stats.p95_ms}  max {stats.max_ms}\n"
        f"target p95 < {LATENCY_TARGET_MS} ms: {'PASS' if passed else 'FAIL'}"
    )
    return LatencyReport(stats, len(matched), expected, passed, text)
