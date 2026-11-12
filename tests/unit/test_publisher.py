import asyncio
import itertools
import json
import time

import pytest

from contracts import Valid, validate
from fleet.transport import TransportUnavailable
from fleet.transport.outbox import Outbox
from fleet.transport.zenoh import StandInZenoh
from fleet.vehicle import signals
from fleet.vehicle.publisher import Publisher
from fleet.vehicle.twin import InMemoryTwin, TwinUnavailable
from tests.harness.clock import FakeClock

pytestmark = pytest.mark.standin
STATE = {
    signals.LAT: 43.9,
    signals.LON: -78.86,
    signals.SPEED: 42.0,
    signals.ACCEL: -0.5,
    signals.TRACTION: False,
    signals.SOC: 58.0,
    signals.COOLANT: 70.0,
    signals.ODOMETER: 3.2,
    signals.TRIP: 1,
    signals.SIM_TIME: 120.0,
}


async def make(buffer_size=60):
    twin, zenoh, clock = InMemoryTwin(signals.ALL), StandInZenoh(), FakeClock()
    await twin.set(STATE)
    got = []

    async def capture(key, payload):
        got.append((key, json.loads(payload)))

    await zenoh.subscribe("fleet/**", capture)
    pub = Publisher("veh-02", twin, zenoh, clock, telemetry_hz=1.0, buffer_size=buffer_size)
    await pub.start()
    return twin, zenoh, clock, pub, got


async def test_req072_one_telemetry_message_per_wall_second():
    _twin, _zenoh, clock, pub, got = await make()

    await pub.run_telemetry(ticks=10)

    assert clock.slept_s == pytest.approx(10.0)
    assert [k for k, _ in got] == ["fleet/veh-02/telemetry"] * 10
    assert all(isinstance(validate(m), Valid) for _, m in got)
    assert got[0][1]["speed_kmh"] == 42.0 and got[0][1]["trip"] == 1


async def test_req072_hazard_change_published_immediately_including_none():
    twin, _zenoh, _clock, _pub, got = await make()

    started = time.perf_counter()
    await twin.set(
        {signals.HAZARD_TYPE: "harsh_braking", signals.HAZARD_SEVERITY: 3, signals.HAZARD_T0: 1234}
    )
    elapsed = time.perf_counter() - started
    await twin.set(
        {signals.HAZARD_TYPE: "none", signals.HAZARD_SEVERITY: 0, signals.HAZARD_T0: 2234}
    )

    hazards = [m for k, m in got if k == "fleet/veh-02/hazard"]
    assert [(m["hazard_type"], m["severity"], m["t0"]) for m in hazards] == [
        ("harsh_braking", 3, 1234),
        ("none", 0, 2234),
    ]
    assert all(isinstance(validate(m), Valid) for m in hazards)
    assert hazards[0]["lat"] == 43.9
    assert elapsed < 0.1


async def test_req074_broker_down_buffers_last_n_and_latest_hazard_then_drains():
    twin, zenoh, clock, pub, got = await make(buffer_size=5)
    zenoh.up = False

    await pub.run_telemetry(ticks=30)
    for t0, kind in [(1, "overspeed"), (2, "harsh_braking")]:
        await twin.set(
            {signals.HAZARD_TYPE: kind, signals.HAZARD_SEVERITY: 1, signals.HAZARD_T0: t0}
        )
    assert got == []

    zenoh.up = True
    for _ in range(50):
        await clock.sleep(1)

    hazards = [m["hazard_type"] for k, m in got if k.endswith("hazard")]
    telemetry = [m for k, m in got if k.endswith("telemetry")]
    assert hazards == ["harsh_braking"]
    assert len(telemetry) == 5
    assert pub.outbox.dropped == 25


async def test_req074_kuksa_unreachable_is_logged_not_fatal(caplog):
    twin, _zenoh, _clock, pub, got = await make()

    async def broken(paths):
        raise TwinUnavailable("databroker unreachable")

    twin.get = broken
    await pub.run_telemetry(ticks=3)

    assert got == []
    assert "databroker unreachable" in caplog.text


async def test_req074_outbox_backs_off_exponentially():
    clock, attempts = FakeClock(), []

    async def always_down(dest, payload):
        attempts.append(clock.ms)
        raise TransportUnavailable("down")

    outbox = Outbox(always_down, clock, buffer_size=3, base_backoff_s=0.5, max_backoff_s=4.0)
    task = asyncio.create_task(outbox.run())
    await outbox.submit("t", b"x")
    for _ in range(20):
        await asyncio.sleep(0)
    task.cancel()

    gaps = [b - a for a, b in itertools.pairwise(attempts)]
    assert gaps[:5] == [0, 500, 1000, 2000, 4000]


class AsyncNotifyTwin(InMemoryTwin):
    """Delivers updates later and in order, like the Kuksa Databroker's subscription stream."""

    async def subscribe(self, paths, on_change):
        queue = asyncio.Queue()

        async def drain():
            while True:
                await on_change(await queue.get())

        asyncio.get_running_loop().create_task(drain())

        async def enqueue(values):
            queue.put_nowait(values)

        await super().subscribe(paths, enqueue)


async def test_req072_one_tick_hazard_is_published_even_if_already_cleared():
    """A hazard that lasts one sim tick (10 ms at 10x) must still reach the cloud (REQ-121)."""
    twin, zenoh, clock = AsyncNotifyTwin(signals.ALL), StandInZenoh(), FakeClock()
    await twin.set(STATE)
    got = []

    async def capture(key, payload):
        got.append(json.loads(payload)["hazard_type"])

    await zenoh.subscribe("fleet/*/hazard", capture)
    await Publisher("veh-02", twin, zenoh, clock, telemetry_hz=1.0, buffer_size=60).start()

    await twin.set(
        {signals.HAZARD_TYPE: "harsh_braking", signals.HAZARD_SEVERITY: 3, signals.HAZARD_T0: 1}
    )
    await twin.set({signals.HAZARD_TYPE: "none", signals.HAZARD_SEVERITY: 0, signals.HAZARD_T0: 11})
    for _ in range(10):
        await asyncio.sleep(0)

    assert got == ["harsh_braking", "none"]
