"""Regenerate committed route fixtures from OSRM. The only code besides the runtime cache that calls OSRM."""

import json
from pathlib import Path

from fleet.config import load_config
from fleet.routes.osrm import osrm_fetch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "routes"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for route in load_config(ROOT / "config" / "fleet.yaml").routes.values():
        polyline = osrm_fetch(route.anchors)
        fixture = {"route": route.id, "anchors": route.anchors, "polyline": polyline}
        (OUT / f"{route.id}.json").write_text(json.dumps(fixture))
        print(f"{route.id}: {len(polyline)} points")


if __name__ == "__main__":
    main()
