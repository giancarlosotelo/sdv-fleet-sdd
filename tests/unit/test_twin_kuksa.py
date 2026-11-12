import asyncio

import grpc
import pytest
from kuksa_client.grpc import Datapoint

from fleet.vehicle import signals
from fleet.vehicle.twin_kuksa import KuksaTwin

pytestmark = pytest.mark.standin  # real adapter logic against a fake gRPC client


class StreamBroken(grpc.RpcError):
    pass


class FakeClient:
    """Each subscribe yields the current values first, then the scripted updates, then breaks."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.subscribes = 0

    async def subscribe_current_values(self, paths):
        self.subscribes += 1
        script = self.streams.pop(0) if self.streams else []
        yield {p: Datapoint(None) for p in paths}
        for update in script:
            yield {signals.SPEED: Datapoint(update)}
        if self.streams:
            raise StreamBroken("databroker restarted")
        await asyncio.Event().wait()


async def test_req074_subscription_resumes_after_stream_breaks():
    client = FakeClient([[10.0], [20.0]])
    twin, seen = KuksaTwin(client, retry_s=0.01), []

    async def on_change(values):
        seen.append(values[signals.SPEED])

    await twin.subscribe([signals.SPEED], on_change)
    for _ in range(100):
        if len(seen) == 2:
            break
        await asyncio.sleep(0.01)
    await twin.close()

    assert seen == [10.0, 20.0]
    assert client.subscribes == 2


async def test_req074_failing_callback_does_not_end_subscription(caplog):
    twin, seen = KuksaTwin(FakeClient([[1.0, 2.0]]), retry_s=0.01), []

    async def on_change(values):
        seen.append(values[signals.SPEED])
        if len(seen) == 1:
            raise ConnectionError("downstream write failed")

    await twin.subscribe([signals.SPEED], on_change)
    for _ in range(100):
        if len(seen) == 2:
            break
        await asyncio.sleep(0.01)
    await twin.close()

    assert seen == [1.0, 2.0]
    assert "downstream write failed" in caplog.text
