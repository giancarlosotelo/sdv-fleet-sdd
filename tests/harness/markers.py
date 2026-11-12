from pathlib import Path

import pytest

from tests.harness.isolation import _imports, _under

# fleet.demo.wiring builds the stand-in or real adapters, so tests using it are adapter tests too.
ADAPTERS = (
    "fleet.vehicle.twin",
    "fleet.vehicle.twin_kuksa",
    "fleet.transport",
    "fleet.demo.wiring",
)
LABELS = ("standin", "real")


def _uses_adapter(path: Path, cache: dict[Path, bool]) -> bool:
    if path not in cache:
        cache[path] = any(_under(m, ADAPTERS) for m in _imports(path))
    return cache[path]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    cache: dict[Path, bool] = {}
    for item in items:
        labels = [m for m in LABELS if item.get_closest_marker(m)]
        if labels:
            item.user_properties.append(("backend", "+".join(labels)))
    unlabelled = [
        item.nodeid
        for item in items
        if _uses_adapter(item.path, cache) and not any(item.get_closest_marker(m) for m in LABELS)
    ]
    if unlabelled:
        lines = [
            f"{nodeid} needs @pytest.mark.standin or @pytest.mark.real" for nodeid in unlabelled
        ]
        raise pytest.UsageError("\n".join(lines))


def pytest_report_teststatus(report: pytest.TestReport, config: pytest.Config):
    """Verbose output names the backend, e.g. `PASSED [standin]` (spec REQ-132)."""
    label = dict(report.user_properties).get("backend")
    if label and (report.when == "call" or (report.when == "setup" and report.skipped)):
        short = {"passed": ".", "failed": "F", "skipped": "s"}[report.outcome]
        return report.outcome, short, f"{report.outcome.upper()} [{label}]"
    return None
