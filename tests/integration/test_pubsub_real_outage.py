import asyncio

import pytest

from fleet.transport import TransportUnavailable


@pytest.mark.real
async def test_req074_publish_to_unreachable_pubsub_fails_fast(monkeypatch):
    """The client would retry for 600 s; the outbox needs a quick failure to start buffering."""
    from fleet.transport import pubsub_real

    monkeypatch.setenv("PUBSUB_EMULATOR_HOST", "127.0.0.1:9")
    monkeypatch.setattr(pubsub_real, "PUBLISH_TIMEOUT_S", 1.0)
    client = pubsub_real.RealPubSub()

    with pytest.raises(TransportUnavailable):
        await asyncio.wait_for(client.publish("telemetry", b"x"), timeout=15)
    await client.close()
