import asyncio
import random

import pytest

from fleet.vehicle import signals
from fleet.vehicle.twin import InMemoryTwin, UnknownSignal
from tests.harness.real import require_service


@pytest.fixture(
    params=[
        pytest.param("standin", marks=pytest.mark.standin),
        pytest.param("real", marks=pytest.mark.real),
    ]
)
async def twin(request):
    if request.param == "standin":
        yield InMemoryTwin(signals.ALL)
        return
    from fleet.vehicle.twin_kuksa import KuksaTwin

    require_service("kuksa databroker", KuksaTwin.BASE_PORT)
    twin = await KuksaTwin.connect(port=KuksaTwin.BASE_PORT)
    yield twin
    await twin.close()


async def eventually(check, timeout_s=2.0):
    for _ in range(int(timeout_s / 0.02)):
        if check():
            return
        await asyncio.sleep(0.02)


async def test_req040_set_then_get(twin):
    speed, trip = round(random.uniform(1, 99), 3), random.randint(1, 10_000)

    await twin.set({signals.SPEED: speed, signals.TRIP: trip, signals.HAZARD_TYPE: "overheat"})

    got = await twin.get([signals.SPEED, signals.TRIP, signals.HAZARD_TYPE])
    assert got[signals.SPEED] == pytest.approx(speed)
    assert (got[signals.TRIP], got[signals.HAZARD_TYPE]) == (trip, "overheat")


async def test_req040_subscriber_sees_only_its_paths(twin):
    seen = []
    speed = round(random.uniform(1, 99), 3)

    async def on_change(values):
        seen.append(values)

    await twin.subscribe([signals.SPEED], on_change)
    await twin.set({signals.SPEED: speed, signals.SOC: random.uniform(1, 99)})
    await twin.set({signals.SOC: random.uniform(1, 99)})
    await eventually(lambda: seen)
    await asyncio.sleep(0.1)

    assert len(seen) == 1 and list(seen[0]) == [signals.SPEED]
    assert seen[0][signals.SPEED] == pytest.approx(speed)


async def test_req040_unknown_signal_is_rejected(twin):
    with pytest.raises(UnknownSignal, match="Vehicle.Bogus"):
        await twin.set({"Vehicle.Bogus": 1})


async def test_req040_each_changed_signal_is_its_own_update(twin):
    """The real databroker notifies per signal even for one multi-signal set; the stand-in must too."""
    seen = []

    async def on_change(values):
        seen.append(values)

    await twin.subscribe([signals.HAZARD_TYPE, signals.HAZARD_SEVERITY], on_change)
    severity = random.randint(1, 3)
    await twin.set({signals.HAZARD_TYPE: "overheat", signals.HAZARD_SEVERITY: severity})
    await eventually(lambda: len(seen) >= 2)
    await asyncio.sleep(0.1)

    assert sorted(seen, key=lambda v: next(iter(v))) == [
        {signals.HAZARD_SEVERITY: severity},
        {signals.HAZARD_TYPE: "overheat"},
    ]
