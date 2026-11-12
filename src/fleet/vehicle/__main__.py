"""One vehicle workload per process, as Ankaios runs them (spec REQ-140)."""

import argparse
import asyncio
import random
from pathlib import Path

from fleet.clock import SystemClock
from fleet.config import load_config
from fleet.routes.cache import load_route
from fleet.transport.zenoh_real import DEFAULT_ENDPOINT, RealZenoh
from fleet.vehicle.detector import Detector
from fleet.vehicle.publisher import Publisher
from fleet.vehicle.simulator import Simulator, run_simulator
from fleet.vehicle.twin_kuksa import KuksaTwin


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
    twin = await KuksaTwin.connect(args.kuksa_host, args.kuksa_port)
    if args.role == "simulator":
        rng = random.Random(f"{cfg.demo.seed}-{van.id}")
        sim = Simulator(van, load_route(van.route), cfg.charging, rng)
        await run_simulator(sim, twin, clock, cfg.demo.time_scale)
    elif args.role == "detector":
        await Detector(twin, van.route.speed_limit_kmh, cfg.thresholds, clock).start()
        await asyncio.Event().wait()
    else:
        publisher = Publisher(
            van.id,
            twin,
            RealZenoh(args.zenoh),
            clock,
            cfg.publisher.telemetry_hz,
            cfg.publisher.buffer_size,
        )
        await publisher.start()
        await publisher.run_telemetry()


def main() -> None:
    asyncio.run(run(parse()))


if __name__ == "__main__":
    main()
