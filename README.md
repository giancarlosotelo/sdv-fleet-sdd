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

## Run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,real]"
.venv/bin/fleet-demo                                  # dashboard at http://127.0.0.1:8000
.venv/bin/fleet-demo --inject-hazards 50              # latency test, PASS/FAIL
.venv/bin/pytest -m "not real" --ignore=tests/pipeline
docker compose -f deploy/compose.yaml up -d && .venv/bin/pytest -m real --ignore=tests/pipeline
```

Pipeline tests need their own venv (Beam and kuksa-client need different protobuf versions):

```bash
python3.12 -m venv .venv-pipeline && .venv-pipeline/bin/pip install -e ".[dev,pipeline]"
.venv-pipeline/bin/pytest tests/pipeline -m "not real"
```
