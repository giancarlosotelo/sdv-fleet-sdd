# SDV Fleet Monitor (SDD build)

SDV Fleet Operations & Hazard Monitor, built from scratch by Claude Code with spec-driven development. Everything here came from one prompt and the product brief.

## Run the prompt

1. Start Claude Code with a clean profile, so only this repo's skills load:

   ```bash
   CLAUDE_CONFIG_DIR=~/.claude-sdd claude
   ```

2. Paste the prompt in [`evals/prompts/v1-kickoff.md`](evals/prompts/v1-kickoff.md). It builds the product in [`docs/product-brief.md`](docs/product-brief.md) by following [`CLAUDE.md`](CLAUDE.md): grill → spec → TDD → verify → review.

To rebuild from zero, check out tag `skills-v1` (only the skills, the brief and the prompt) and run the prompt there.

## What's here

| Path | What |
|---|---|
| `.claude/skills/` | The 5 SDD skills ([sources and why](skills-vendor/VENDOR.md)) |
| `docs/product-brief.md` | What to build |
| `specs/` | Spec (44 requirements), plan and tasks the agent wrote |
| `measurements/dev-log.csv` | Time, defects and rework per step |
| `src/`, `tests/` | The product and its tests |

How it compares with the MVP: [`docs/mvp-vs-v1-comparison.md`](docs/mvp-vs-v1-comparison.md).

## Run it locally

### 1. Prerequisites

- Python 3.12 exactly (`brew install python@3.12` on macOS). 3.13 is not supported.
- Docker, only for the real Kuksa, Zenoh and Pub/Sub services (step 4).
- Internet on the first demo run: route geometry is fetched from OpenStreetMap once and cached in `.cache/`. Tests never use the network.

### 2. Install

Two virtual environments, because Beam and kuksa-client need different protobuf versions:

```bash
git clone https://github.com/giancarlosotelo/sdv-fleet-sdd.git && cd sdv-fleet-sdd
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,real]"
python3.12 -m venv .venv-pipeline && .venv-pipeline/bin/pip install -e ".[dev,pipeline]"
```

### 3. Demo with stand-ins (no Docker)

```bash
.venv/bin/fleet-demo                          # 3 vans, cloud service and dashboard in one process
```

Open http://127.0.0.1:8000: vans moving on the map, alerts arriving, the latency panel, and the route table after the first trips (about 2 minutes). Stop with Ctrl+C.

| Option | What it does |
|---|---|
| `--inject-hazards 50` | Injects 50 hazards through the full path, prints median, p95 and max latency, exits with PASS or FAIL |
| `--port 8080` | Another port (default 8000) |
| `--time-scale 25` | Vans move faster (default 10) |
| `--seed 7` | A different but repeatable run (default 42) |
| `--capture out/cap.jsonl` | Saves every message, to feed the pipeline later |

### 4. Demo with real services (Docker)

```bash
docker compose -f deploy/compose.yaml up -d   # 3 Kuksa databrokers (55561-55563), Zenoh (7447), Pub/Sub emulator (8085)
.venv/bin/fleet-demo --real-kuksa --real-zenoh --real-pubsub
.venv/bin/fleet-demo --real-kuksa --real-zenoh --real-pubsub --inject-hazards 50
docker compose -f deploy/compose.yaml down
```

The flags are independent, so you can swap in one real service at a time.

### 5. Data pipeline (Beam)

```bash
.venv-pipeline/bin/python -m fleet.pipeline --input contracts/samples/ --db out/fleet.db   # sample data
.venv-pipeline/bin/python -m fleet.pipeline --input out/cap.jsonl --db out/fleet.db        # a captured demo run
```

Valid messages go to the `telemetry`, `alerts` and `trips` tables; malformed ones go to `quarantine`. Beam prints "Unparseable argument" warnings for the script's own flags; they are harmless.

### 6. Tests

```bash
.venv/bin/pytest -m "not real" --ignore=tests/pipeline    # unit + stand-in, network blocked
.venv/bin/pytest -m real --ignore=tests/pipeline          # needs step 4's docker compose
.venv-pipeline/bin/pytest tests/pipeline                  # pipeline
.venv/bin/ruff check . && .venv/bin/ruff format --check . # lint
```

Tests that need a real service skip with the command to start it. `FLEET_REQUIRE_REAL=1` makes them fail instead (CI does this).
