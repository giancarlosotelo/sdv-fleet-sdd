from pathlib import Path

import pytest

from tests.harness.isolation import _imports, _under

ADAPTERS = ("fleet.vehicle.twin", "fleet.vehicle.twin_kuksa", "fleet.transport")
LABELS = ("standin", "real")


def _uses_adapter(path: Path, cache: dict[Path, bool]) -> bool:
    if path not in cache:
        cache[path] = any(_under(m, ADAPTERS) for m in _imports(path))
    return cache[path]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    cache: dict[Path, bool] = {}
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
