from pathlib import Path

from tests.harness.isolation import check_isolation


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_req070_vehicle_importing_cloud_is_a_violation(tmp_path):
    _write(tmp_path, "fleet/vehicle/detector.py", "from fleet.cloud.alerts import x\n")

    violations = check_isolation(tmp_path)

    assert [(v.file.name, v.imported) for v in violations] == [
        ("detector.py", "fleet.cloud.alerts")
    ]


def test_req070_cloud_importing_vehicle_is_a_violation(tmp_path):
    _write(tmp_path, "fleet/dashboard/app.py", "import fleet.vehicle.simulator\n")

    assert [v.imported for v in check_isolation(tmp_path)] == ["fleet.vehicle.simulator"]


def test_req070_shared_modules_are_allowed_on_both_sides(tmp_path):
    shared = "import contracts\nfrom fleet.config import load\nfrom fleet.transport import zenoh\n"
    _write(tmp_path, "fleet/vehicle/publisher.py", shared)
    _write(tmp_path, "fleet/cloud/service.py", shared)

    assert check_isolation(tmp_path) == []


def test_req070_real_source_tree_is_isolated():
    src = Path(__file__).resolve().parents[1] / "src"

    assert check_isolation(src) == []
