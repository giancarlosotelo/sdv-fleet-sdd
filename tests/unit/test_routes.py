import httpx
import pytest

from fleet.config import Profile, Route
from fleet.routes.cache import RouteUnavailable, load_route
from fleet.routes.osrm import RouteFetchError, osrm_fetch

ANCHORS = ((43.9, -78.9), (43.95, -78.8))


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(coords: list[list[float]]) -> httpx.Response:
    return httpx.Response(
        200, json={"code": "Ok", "routes": [{"geometry": {"coordinates": coords}}]}
    )


def test_req010_osrm_fetch_requests_closed_loop_and_returns_lat_lon():
    seen = []

    def handler(request):
        seen.append(request.url)
        return _ok([[-78.9, 43.9], [-78.8, 43.95], [-78.9, 43.9]])

    polyline = osrm_fetch(ANCHORS, client=_client(handler))

    assert polyline == ((43.9, -78.9), (43.95, -78.8), (43.9, -78.9))
    assert seen[0].path == "/route/v1/driving/-78.9,43.9;-78.8,43.95;-78.9,43.9"
    assert seen[0].params["geometries"] == "geojson"
    assert seen[0].params["overview"] == "full"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"code": "NoRoute", "routes": []}),
        httpx.Response(503, text="busy"),
    ],
    ids=["no-route", "http-503"],
)
def test_req011_osrm_failure_raises_fetch_error(response):
    with pytest.raises(RouteFetchError):
        osrm_fetch(ANCHORS, client=_client(lambda request: response))


def test_req011_osrm_unreachable_raises_fetch_error():
    def handler(request):
        raise httpx.ConnectError("unreachable")

    with pytest.raises(RouteFetchError, match="unreachable"):
        osrm_fetch(ANCHORS, client=_client(handler))


class FakeOsrm:
    def __init__(self, fail: bool = False):
        self.calls = 0
        self.fail = fail

    def __call__(self, anchors):
        self.calls += 1
        if self.fail:
            raise RouteFetchError("unreachable")
        return (*anchors, (43.97, -78.85), anchors[0])


def _route(anchors=ANCHORS) -> Route:
    profile = Profile(
        stops_per_km=1, harsh_brake_share=0.1, traction_events_per_km=0, speeding_tendency=0
    )
    return Route(id="A", name="North", speed_limit_kmh=60, anchors=anchors, profile=profile)


def test_req010_cache_miss_fetches_once_and_returns_closed_loop(tmp_path):
    fetch = FakeOsrm()

    polyline = load_route(_route(), tmp_path, fetch=fetch)

    assert fetch.calls == 1
    assert polyline[0] == polyline[-1] == ANCHORS[0]
    assert [p.name.split("-")[0] for p in tmp_path.iterdir()] == ["A"]


def test_req010_cache_hit_makes_no_fetch(tmp_path):
    first = load_route(_route(), tmp_path, fetch=FakeOsrm())
    fetch = FakeOsrm()

    assert load_route(_route(), tmp_path, fetch=fetch) == first
    assert fetch.calls == 0


def test_req010_changed_anchors_refetch(tmp_path):
    load_route(_route(), tmp_path, fetch=FakeOsrm())
    fetch = FakeOsrm()

    load_route(_route(anchors=((43.8, -78.9), (43.95, -78.8))), tmp_path, fetch=fetch)

    assert fetch.calls == 1


def test_req011_miss_with_osrm_unreachable_names_route(tmp_path):
    with pytest.raises(RouteUnavailable, match="route A"):
        load_route(_route(), tmp_path, fetch=FakeOsrm(fail=True))
