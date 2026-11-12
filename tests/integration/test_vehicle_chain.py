import json
import random
from pathlib import Path

import pytest

from contracts import HAZARD_TOPIC, TELEMETRY_TOPIC, Valid, validate
from fleet.config import load_config
from fleet.transport.bridge import Bridge
from fleet.transport.pubsub import StandInPubSub
from fleet.transport.zenoh import StandInZenoh
from fleet.vehicle import signals
from fleet.vehicle.detector import Detector
from fleet.vehicle.publisher import Publisher
from fleet.vehicle.simulator import Simulator, run_simulator
from fleet.vehicle.twin import InMemoryTwin
from tests.harness.clock import FakeClock
from tests.harness.routes import fixture_polyline

pytestmark = pytest.mark.standin
CFG = load_config(Path(__file__).resolve().parents[2] / "config" / "fleet.yaml")


async def test_m2_seeded_van_hazards_reach_pubsub():
    van = next(v for v in CFG.vehicles if v.id == "veh-02")
    twin, zenoh, pubsub, clock = (
        InMemoryTwin(signals.ALL),
        StandInZenoh(),
        StandInPubSub(),
        FakeClock(),
    )
    received = {HAZARD_TOPIC: [], TELEMETRY_TOPIC: []}
    for topic, bucket in received.items():

        async def keep(data, bucket=bucket):
            bucket.append(json.loads(data))

        await pubsub.subscribe(topic, keep)
    await Bridge(zenoh, pubsub, clock, buffer_size=60).start()
    publisher = Publisher(van.id, twin, zenoh, clock, telemetry_hz=1.0, buffer_size=60)
    await publisher.start()
    await Detector(twin, van.route.speed_limit_kmh, CFG.thresholds, clock).start()
    sim = Simulator(van, fixture_polyline("B"), CFG.charging, random.Random("42-veh-02"))

    await run_simulator(sim, twin, clock, time_scale=10.0, dt_s=0.1, ticks=6000)
    await publisher.run_telemetry(ticks=1)

    hazards = received[HAZARD_TOPIC]
    assert any(h["hazard_type"] == "harsh_braking" for h in hazards)
    assert all(isinstance(validate(m), Valid) for m in hazards + received[TELEMETRY_TOPIC])
    assert received[TELEMETRY_TOPIC][0]["vehicle_id"] == "veh-02"
    assert {h["hazard_type"] for h in hazards} >= {"harsh_braking", "none"}
