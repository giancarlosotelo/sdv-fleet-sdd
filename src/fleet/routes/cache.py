import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from fleet.config import Route
from fleet.routes.osrm import Point, Polyline, RouteFetchError, osrm_fetch

DEFAULT_CACHE_DIR = Path(".cache/routes")


class RouteUnavailable(RuntimeError):
    pass


def _cache_file(route: Route, cache_dir: Path) -> Path:
    digest = hashlib.sha256(json.dumps(route.anchors).encode()).hexdigest()[:12]
    return cache_dir / f"{route.id}-{digest}.json"


def load_route(
    route: Route,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetch: Callable[[tuple[Point, ...]], Polyline] = osrm_fetch,
) -> Polyline:
    """Cached road geometry for a route; fetches from OSRM only on a cache miss."""
    path = _cache_file(route, cache_dir)
    if path.exists():
        return tuple(tuple(p) for p in json.loads(path.read_text()))
    try:
        polyline = fetch(route.anchors)
    except RouteFetchError as ex:
        raise RouteUnavailable(f"route {route.id}: no cached geometry and {ex}") from ex
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(polyline))
    return polyline
