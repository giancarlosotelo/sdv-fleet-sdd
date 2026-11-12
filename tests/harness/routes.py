import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "routes"


def fixture_polyline(route_id: str) -> tuple[tuple[float, float], ...]:
    data = json.loads((FIXTURES / f"{route_id}.json").read_text())
    return tuple(tuple(p) for p in data["polyline"])
