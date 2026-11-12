import pytest

from fleet.transport import TransportUnavailable
from fleet.vehicle.__main__ import connect_with_retry
from tests.harness.clock import FakeClock

pytestmark = pytest.mark.standin


async def test_req074_workload_retries_connecting_until_service_is_up(caplog):
    clock, attempts = FakeClock(), []

    async def connect():
        attempts.append(clock.ms)
        if len(attempts) < 3:
            raise TransportUnavailable("zenoh router down")
        return "session"

    assert await connect_with_retry(connect, clock, "zenoh") == "session"
    assert len(attempts) == 3 and "zenoh router down" in caplog.text
