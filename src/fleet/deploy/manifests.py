"""Ankaios manifests generated from the fleet config: one per van (spec REQ-140)."""

import argparse
from pathlib import Path
from typing import Any

import yaml

from fleet.config import FleetConfig, Vehicle, load_config

API_VERSION = "v0.1"
DATABROKER_IMAGE = "ghcr.io/eclipse-kuksa/kuksa-databroker:0.6.0"
VEHICLE_IMAGE = "fleet-vehicle:0.1.0"  # built from deploy/Dockerfile
BASE_PORT = 55561  # matches KuksaTwin.BASE_PORT and deploy/compose.yaml
ZENOH_ENDPOINT = "tcp/127.0.0.1:7447"
WORKLOADS = ("databroker", "simulator", "detector", "publisher")


def _runtime(image: str, args: list[str], volumes: list[str] = ()) -> str:
    options = ["--net=host", *(f"-v={v}" for v in volumes)]
    return yaml.safe_dump({"image": image, "commandOptions": options, "commandArgs": args})


def manifest_for(cfg: FleetConfig, van: Vehicle, index: int) -> dict[str, Any]:
    port = str(BASE_PORT + index)
    vss = "/vss_release_5.1.json,/overlay/overlay.json"
    workloads: dict[str, Any] = {
        "databroker": {
            "runtime": "podman",
            "agent": van.id,
            "restartPolicy": "ALWAYS",
            "runtimeConfig": _runtime(
                DATABROKER_IMAGE,
                ["--insecure", "--port", port, "--vss", vss],
                volumes=["/opt/fleet/vss:/overlay:ro"],
            ),
        }
    }
    for role in WORKLOADS[1:]:
        args = [role, "--vehicle", van.id, "--kuksa-port", port, "--zenoh", ZENOH_ENDPOINT]
        workloads[role] = {
            "runtime": "podman",
            "agent": van.id,
            "restartPolicy": "ALWAYS",
            "dependencies": {"databroker": "ADD_COND_RUNNING"},
            "runtimeConfig": _runtime(VEHICLE_IMAGE, args),
        }
    return {"apiVersion": API_VERSION, "workloads": workloads}


def write_manifests(cfg: FleetConfig, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, van in enumerate(cfg.vehicles):
        path = out / f"{van.id}.yaml"
        path.write_text(yaml.safe_dump(manifest_for(cfg, van, i), sort_keys=False))
        paths.append(path)
    return paths


def main() -> None:
    p = argparse.ArgumentParser(prog="fleet.deploy.manifests")
    p.add_argument("--config", type=Path, default=Path("config/fleet.yaml"))
    p.add_argument("--out", type=Path, default=Path("deploy/ankaios"))
    args = p.parse_args()
    for path in write_manifests(load_config(args.config), args.out):
        print(path)


if __name__ == "__main__":
    main()
