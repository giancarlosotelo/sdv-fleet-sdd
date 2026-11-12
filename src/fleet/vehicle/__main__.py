"""One vehicle workload per process, as Ankaios runs them (spec REQ-140)."""

import argparse
import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from pathlib import Path

from fleet.clock import Clock, SystemClock
from fleet.config import load_config
from fleet.routes.cache import load_route
from fleet.transport import TransportUnavailable
from fleet.transport.zenoh_real import DEFAULT_ENDPOINT, RealZenoh
from fleet.vehicle.detector import Detector
from fleet.vehicle.publisher import Publisher
from fleet.vehicle.simulator import Simulator, run_simulator
from fleet.vehicle.twin import TwinUnavailable
from fleet.vehicle.twin_kuksa import KuksaTwin

log = logging.getLogger(__name__)


async def connect_with_retry[T](connect: Callable[[], Awaitable[T]], clock: Clock, what: str) -> T:
    """Workloads start before their services may be up: retry with backoff, never crash (REQ-074)."""
    backoff = 0.5
    while True:
        try:
            return await connect()
        except (TwinUnavailable, TransportUnavailable) as ex:
            log.warning("%s not reachable, retrying in %.1f s: %s", what, backoff, ex)
            await clock.sleep(backoff)
            backoff = min(backoff * 2, 8.0)


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="fleet.vehicle")
    p.add_argument("role", choices=["simulator", "detector", "publisher"])
    p.add_argument("--vehicle", required=True)
    p.add_argument("--config", type=Path, default=Path("config/fleet.yaml"))
    p.add_argument("--kuksa-host", default="127.0.0.1")
    p.add_argument("--kuksa-port", type=int, default=KuksaTwin.BASE_PORT)
    p.add_argument("--zenoh", default=DEFAULT_ENDPOINT)
    return p.parse_args(argv)


async def run(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    van = next(v for v in cfg.vehicles if v.id == args.vehicle)
    clock = SystemClock()
    twin = await connect_with_retry(
        lambda: KuksaTwin.connect(args.kuksa_host, args.kuksa_port), clock, "kuksa databroker"
    )
    if args.role == "simulator":
        rng = random.Random(f"{cfg.demo.seed}-{van.id}")
        sim = Simulator(van, load_route(van.route), cfg.charging, rng)
        await run_simulator(sim, twin, clock, cfg.demo.time_scale)
    elif args.role == "detector":
        await Detector(twin, van.route.speed_limit_kmh, cfg.thresholds, clock).start()
        await asyncio.Event().wait()
    else:

        async def open_zenoh() -> RealZenoh:
            return RealZenoh(args.zenoh)

        zenoh = await connect_with_retry(open_zenoh, clock, "zenoh router")
        publisher = Publisher(
            van.id,
            twin,
            zenoh,
            clock,
            cfg.publisher.telemetry_hz,
            cfg.publisher.buffer_size,
        )
        await publisher.start()
        await publisher.run_telemetry()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(parse()))


if __name__ == "__main__":
    main()
