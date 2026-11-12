"""Wires vans, transport, cloud service and dashboard into one process (spec REQ-120)."""

import asyncio
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from contracts import HAZARD_TOPIC, TELEMETRY_TOPIC
from fleet.clock import Clock, SystemClock
from fleet.cloud.service import CloudService
from fleet.cloud.storage import SqliteStorage
from fleet.config import FleetConfig
from fleet.dashboard.app import create_app
from fleet.transport.bridge import Bridge
from fleet.transport.pubsub import PubSub, StandInPubSub
from fleet.transport.zenoh import StandInZenoh, Zenoh
from fleet.vehicle import signals
from fleet.vehicle.detector import Detector
from fleet.vehicle.publisher import Publisher
from fleet.vehicle.simulator import Simulator, run_simulator
from fleet.vehicle.twin import InMemoryTwin, Twin

Polyline = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class DemoOptions:
    port: int = 8000
    time_scale: float = 10.0
    seed: int = 42
    db: Path = Path("out/fleet.db")
    capture: Path | None = None
    real_kuksa: bool = False
    real_zenoh: bool = False
    real_pubsub: bool = False
    dt_s: float = 0.1


@dataclass
class Demo:
    cfg: FleetConfig
    opts: DemoOptions
    clock: Clock
    storage: SqliteStorage
    service: CloudService
    bridge: Bridge
    twins: dict[str, Twin]
    sims: dict[str, Simulator]
    publishers: dict[str, Publisher]
    server: uvicorn.Server
    vehicle_zenoh: Zenoh
    service_pubsub: PubSub
    tasks: list[asyncio.Task] = field(default_factory=list)

    async def start(self) -> None:
        self.service.run_in_background()
        for vid, sim in self.sims.items():
            self.tasks.append(
                asyncio.create_task(
                    run_simulator(
                        sim, self.twins[vid], self.clock, self.opts.time_scale, self.opts.dt_s
                    )
                )
            )
            self.publishers[vid].run_in_background()
        self.tasks.append(asyncio.create_task(self.server.serve()))

    async def stop(self) -> None:
        self.server.should_exit = True
        for task in self.tasks:
            if task is not self.tasks[-1]:
                task.cancel()
        for pub in self.publishers.values():
            await pub.stop()
        await self.bridge.stop()
        if self.service._task:
            self.service._task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for adapter in (*self.twins.values(), self.vehicle_zenoh, self.service_pubsub):
            close = getattr(adapter, "close", None)  # only the real adapters hold connections
            if close:
                await close()
        self.storage.close()


def _zenoh(opts: DemoOptions) -> Zenoh:
    if opts.real_zenoh:
        from fleet.transport.zenoh_real import RealZenoh

        return RealZenoh()
    return StandInZenoh()


def _pubsub(opts: DemoOptions) -> PubSub:
    if opts.real_pubsub:
        from fleet.transport.pubsub_real import RealPubSub

        return RealPubSub()
    return StandInPubSub()


async def _twin(opts: DemoOptions, index: int) -> Twin:
    if opts.real_kuksa:
        from fleet.vehicle.twin_kuksa import KuksaTwin

        return await KuksaTwin.connect(port=KuksaTwin.BASE_PORT + index)
    return InMemoryTwin(signals.ALL)


async def _capture(pubsub: PubSub, path: Path, clock: Clock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = path.open("w")

    async def write(data: bytes) -> None:
        out.write(json.dumps({"received_ms": clock.now_ms(), "payload": data.decode()}) + "\n")
        out.flush()

    await pubsub.subscribe(TELEMETRY_TOPIC, write)
    await pubsub.subscribe(HAZARD_TOPIC, write)


async def build_demo(
    cfg: FleetConfig, routes: dict[str, Polyline], opts: DemoOptions, clock: Clock | None = None
) -> Demo:
    clock = clock or SystemClock()
    zenoh, pubsub = _zenoh(opts), _pubsub(opts)
    opts.db.parent.mkdir(parents=True, exist_ok=True)
    storage = SqliteStorage(opts.db)
    service = CloudService(cfg, storage, clock)
    await service.start(pubsub)
    if opts.capture:
        await _capture(pubsub, opts.capture, clock)
    bridge = Bridge(zenoh, pubsub, clock, cfg.publisher.buffer_size)
    await bridge.start()
    twins, sims, publishers = {}, {}, {}
    for i, van in enumerate(cfg.vehicles):
        twin = await _twin(opts, i)
        await Detector(twin, van.route.speed_limit_kmh, cfg.thresholds, clock).start()
        publisher = Publisher(
            van.id, twin, zenoh, clock, cfg.publisher.telemetry_hz, cfg.publisher.buffer_size
        )
        await publisher.start()
        rng = random.Random(f"{opts.seed}-{van.id}")
        twins[van.id], publishers[van.id] = twin, publisher
        sims[van.id] = Simulator(van, routes[van.route.id], cfg.charging, rng)
    app = create_app(service, cfg, routes)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=opts.port, log_level="warning")
    )
    return Demo(
        cfg, opts, clock, storage, service, bridge, twins, sims, publishers, server, zenoh, pubsub
    )
