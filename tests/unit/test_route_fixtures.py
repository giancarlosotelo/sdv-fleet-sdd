import itertools
import json
import math
from pathlib import Path

import pytest

from fleet.config import load_config

ROOT = Path(__file__).resolve().parents[2]
ROUTES = load_config(ROOT / "config" / "fleet.yaml").routes
# Loop lengths measured with OSRM when the anchors were chosen (2026-11-11).
EXPECTED_KM = {"A": 10.1, "B": 4.3, "C": 12.8}


def _metres(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _fixture(route_id: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "routes" / f"{route_id}.json").read_text())


@pytest.mark.parametrize("route_id", sorted(ROUTES))
def test_req012_fixture_matches_config_anchors(route_id):
    """Fails when config anchors change: re-run scripts/gen_route_fixtures.py."""
    anchors = [list(a) for a in ROUTES[route_id].anchors]

    assert _fixture(route_id)["anchors"] == anchors


@pytest.mark.parametrize("route_id", sorted(ROUTES))
def test_req010_fixture_is_closed_loop_at_first_anchor(route_id):
    polyline = _fixture(route_id)["polyline"]

    assert polyline[0] == polyline[-1]
    assert _metres(polyline[0], ROUTES[route_id].anchors[0]) < 50


@pytest.mark.parametrize("route_id", sorted(ROUTES))
def test_req010_fixture_length_matches_osrm_check(route_id):
    polyline = _fixture(route_id)["polyline"]

    km = sum(_metres(a, b) for a, b in itertools.pairwise(polyline)) / 1000

    assert km == pytest.approx(EXPECTED_KM[route_id], rel=0.05)
