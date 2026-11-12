import httpx

OSRM_URL = "https://router.project-osrm.org"

Point = tuple[float, float]
Polyline = tuple[Point, ...]


class RouteFetchError(RuntimeError):
    pass


def osrm_fetch(anchors: tuple[Point, ...], client: httpx.Client | None = None) -> Polyline:
    """Road-snapped loop through the anchors and back to the first; points are (lat, lon)."""
    loop = (*anchors, anchors[0])
    coords = ";".join(f"{lon},{lat}" for lat, lon in loop)
    client = client or httpx.Client(timeout=30)
    try:
        response = client.get(
            f"{OSRM_URL}/route/v1/driving/{coords}",
            params={"overview": "full", "geometries": "geojson"},
        )
        response.raise_for_status()
    except httpx.HTTPError as ex:
        raise RouteFetchError(f"OSRM request failed: {ex}") from ex
    body = response.json()
    if body.get("code") != "Ok":
        raise RouteFetchError(f"OSRM returned {body.get('code')!r}")
    return tuple((lat, lon) for lon, lat in body["routes"][0]["geometry"]["coordinates"])
