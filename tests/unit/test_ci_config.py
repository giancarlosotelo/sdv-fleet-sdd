from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _workflow() -> dict:
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads the bare key `on` as True
    return data


def _commands(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_req142_runs_on_every_pull_request():
    assert "pull_request" in _workflow()["on"]


def test_req142_standin_job_runs_lint_unit_standin_and_pipeline():
    commands = _commands(_workflow()["jobs"]["standin"])

    assert 'pytest -m "not real" --ignore=tests/pipeline' in commands
    assert ".venv-pipeline/bin/pytest tests/pipeline" in commands
    assert "playwright install" in commands and "ruff check" in commands


def test_req142_real_job_starts_services_and_forbids_skips():
    job = _workflow()["jobs"]["real"]
    commands = _commands(job)

    assert job["env"]["FLEET_REQUIRE_REAL"] == "1"
    assert "docker compose -f deploy/compose.yaml up -d" in commands
    assert "pytest -m real --ignore=tests/pipeline" in commands
    assert "pytest tests/pipeline -m real" in commands


def test_req141_compose_has_pinned_kuksa_zenoh_and_pubsub():
    services = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text())["services"]
    brokers = [s for name, s in services.items() if name.startswith("databroker")]

    assert len(brokers) == 3
    assert all("/overlay/overlay.json" in " ".join(b["command"]) for b in brokers)
    assert {"zenoh", "pubsub"} <= set(services)
    images = [s["image"] for s in services.values()]
    assert all(
        ("@sha256:" in i or ":" in i.rsplit("/", 1)[-1]) and not i.endswith(":latest")
        for i in images
    )
