import pytest

from fleet.transport.zenoh import key_matches

pytestmark = pytest.mark.standin


@pytest.mark.parametrize(
    ("expr", "key", "expected"),
    [
        ("fleet/*/hazard", "fleet/veh-01/hazard", True),
        ("fleet/*/hazard", "fleet/veh-01/telemetry", False),
        ("fleet/*/hazard", "fleet/a/b/hazard", False),
        ("fleet/**", "fleet/veh-01/hazard", True),
        ("fleet/**/hazard", "fleet/a/b/hazard", True),
        ("fleet/veh-01/hazard", "fleet/veh-01/hazard", True),
    ],
)
def test_req071_key_expression_matching(expr, key, expected):
    assert key_matches(expr, key) is expected
