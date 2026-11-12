from pathlib import Path

import pytest
import yaml

from fleet.config import load_config
from fleet.deploy.manifests import WORKLOADS, manifest_for, write_manifests
from fleet.vehicle.__main__ import parse

ROOT = Path(__file__).resolve().parents[2]
CFG = load_config(ROOT / "config" / "fleet.yaml")


def test_req140_one_manifest_per_van_with_four_restarting_workloads(tmp_path):
    paths = write_manifests(CFG, tmp_path)

    assert [p.name for p in paths] == ["veh-01.yaml", "veh-02.yaml", "veh-03.yaml"]
    for path, van in zip(paths, CFG.vehicles):
        manifest = yaml.safe_load(path.read_text())
        workloads = manifest["workloads"]
        assert manifest["apiVersion"].startswith("v")
        assert sorted(workloads) == sorted(WORKLOADS)
        assert all(w["restartPolicy"] == "ALWAYS" for w in workloads.values())
        assert all(w["agent"] == van.id for w in workloads.values())


@pytest.mark.parametrize("role", ["simulator", "detector", "publisher"])
def test_req140_vehicle_workloads_get_their_van_id_and_databroker_port(role):
    van = CFG.vehicles[1]
    workload = manifest_for(CFG, van, index=1)["workloads"][role]
    config = yaml.safe_load(workload["runtimeConfig"])

    args = config["commandArgs"]
    assert args[:3] == [role, "--vehicle", "veh-02"]
    assert args[args.index("--kuksa-port") + 1] == "55562"
    assert workload["dependencies"] == {"databroker": "ADD_COND_RUNNING"}


def test_req140_databroker_loads_the_overlay_on_the_van_port():
    workload = manifest_for(CFG, CFG.vehicles[2], index=2)["workloads"]["databroker"]
    config = yaml.safe_load(workload["runtimeConfig"])

    assert "--port" in config["commandArgs"] and "55563" in config["commandArgs"]
    assert any("overlay.json" in a for a in config["commandArgs"])


def test_req001_extra_van_entry_gets_a_manifest(tmp_path):
    cfg = load_config(ROOT / "tests" / "fixtures" / "fleet-4vans.yaml")

    assert [p.stem for p in write_manifests(cfg, tmp_path)][-1] == "veh-04"


def test_req140_entrypoint_args_match_manifest():
    args = parse(["publisher", "--vehicle", "veh-03", "--kuksa-port", "55563"])

    assert (args.role, args.vehicle, args.kuksa_port) == ("publisher", "veh-03", 55563)
