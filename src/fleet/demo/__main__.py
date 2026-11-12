import argparse
import asyncio
import sys
from pathlib import Path

from fleet.config import load_config
from fleet.demo.inject import inject_hazards
from fleet.demo.report import latency_report
from fleet.demo.wiring import DemoOptions, build_demo
from fleet.routes.cache import RouteUnavailable, load_route

WARM_UP_S = 2.0


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="fleet-demo", description="SDV fleet monitor laptop demo")
    p.add_argument("--config", type=Path, default=Path("config/fleet.yaml"))
    p.add_argument("--port", type=int)
    p.add_argument("--time-scale", type=float)
    p.add_argument("--seed", type=int)
    p.add_argument("--inject-hazards", type=int, metavar="N", default=0)
    p.add_argument("--capture", type=Path, metavar="FILE")
    p.add_argument("--real-kuksa", action="store_true")
    p.add_argument("--real-zenoh", action="store_true")
    p.add_argument("--real-pubsub", action="store_true")
    return p.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    try:
        routes = {rid: load_route(route) for rid, route in cfg.routes.items()}
    except RouteUnavailable as ex:
        print(f"fleet-demo: {ex}", file=sys.stderr)
        return 2
    opts = DemoOptions(
        port=args.port or cfg.demo.port,
        time_scale=args.time_scale or cfg.demo.time_scale,
        seed=cfg.demo.seed if args.seed is None else args.seed,
        capture=args.capture,
        real_kuksa=args.real_kuksa,
        real_zenoh=args.real_zenoh,
        real_pubsub=args.real_pubsub,
    )
    demo = await build_demo(cfg, routes, opts)
    await demo.start()
    print(f"dashboard: http://127.0.0.1:{opts.port}", flush=True)
    if not args.inject_hazards:
        await demo.tasks[-1]
        return 0
    try:
        await asyncio.sleep(WARM_UP_S)
        injections = await inject_hazards(demo, args.inject_hazards)
        await asyncio.sleep(1.0)
        report = latency_report(demo, injections)
        print(report.text, flush=True)
        return 0 if report.passed else 1
    finally:
        await demo.stop()


def main() -> None:
    sys.exit(asyncio.run(run(parse(sys.argv[1:]))))


if __name__ == "__main__":
    main()
