import asyncio

import pytest

from contracts import HAZARD_TOPIC, TELEMETRY_TOPIC, hazard_key, telemetry_key
from fleet.transport import TransportUnavailable
from fleet.transport.bridge import Bridge
from fleet.transport.pubsub import StandInPubSub
from fleet.transport.zenoh import StandInZenoh
from tests.harness.clock import FakeClock
from tests.harness.real import require_service

BACKENDS = [
    pytest.param("standin", marks=pytest.mark.standin),
    pytest.param("real", marks=pytest.mark.real),
]


@pytest.fixture(params=BACKENDS)
async def zenoh(request):
    if request.param == "standin":
        yield StandInZenoh()
        return
    from fleet.transport.zenoh_real import RealZenoh

    require_service("zenoh router", 7447)
    session = RealZenoh()
    yield session
    await session.close()


@pytest.fixture(params=BACKENDS)
async def pubsub(request):
    if request.param == "standin":
        yield StandInPubSub()
        return
    from fleet.transport.pubsub_real import RealPubSub

    require_service("pubsub emulator", 8085)
    client = RealPubSub()
    yield client
    await client.close()


def collector():
    got = []

    async def handler(*args):
        got.append(args)

    return got, handler


async def until(check, timeout_s=5.0):
    for _ in range(int(timeout_s / 0.02)):
        if check():
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.2)  # let any unexpected extra delivery arrive


async def test_req071_zenoh_wildcard_subscription_gets_matching_keys(zenoh):
    got, handler = collector()
    await zenoh.subscribe("fleet/*/hazard", handler)
    await asyncio.sleep(0.2)

    await zenoh.put(hazard_key("veh-01"), b"h1")
    await zenoh.put(telemetry_key("veh-01"), b"t1")
    await zenoh.put(hazard_key("veh-02"), b"h2")
    await until(lambda: len(got) >= 2)

    assert got == [("fleet/veh-01/hazard", b"h1"), ("fleet/veh-02/hazard", b"h2")]


async def test_req073_pubsub_delivers_per_topic(pubsub):
    got, handler = collector()
    await pubsub.subscribe(HAZARD_TOPIC, handler)

    await pubsub.publish(HAZARD_TOPIC, b"h")
    await pubsub.publish(TELEMETRY_TOPIC, b"t")
    await until(lambda: got)

    assert got == [(b"h",)]


async def test_req073_bridge_forwards_body_unchanged(zenoh, pubsub):
    telemetry, on_telemetry = collector()
    hazards, on_hazard = collector()
    await pubsub.subscribe(TELEMETRY_TOPIC, on_telemetry)
    await pubsub.subscribe(HAZARD_TOPIC, on_hazard)
    bridge = Bridge(zenoh, pubsub, FakeClock(), buffer_size=10)
    await bridge.start()
    await asyncio.sleep(0.2)
    body = b'{"msg_id": "6f1c2a3e-0b4d-4e5f-8a9b-1c2d3e4f5a60", "x": 1}'

    await zenoh.put(telemetry_key("veh-03"), body)
    await zenoh.put(hazard_key("veh-03"), b"hz")
    await until(lambda: telemetry and hazards)
    await bridge.stop()

    assert telemetry == [(body,)]
    assert hazards == [(b"hz",)]


@pytest.mark.standin
async def test_req074_standin_can_be_taken_down():
    zenoh = StandInZenoh()
    zenoh.up = False

    with pytest.raises(TransportUnavailable):
        await zenoh.put("fleet/veh-01/telemetry", b"x")
