# SDV Fleet Monitor (SDD rebuild)

SDV Fleet Operations & Hazard Monitor, built from scratch with spec-driven development. The product brief is in `docs/product-brief.md`.
Don't read or copy from any other project; everything comes from the brief and the specs.

## Workflow

Every feature goes through these steps, in order, using the skills in `.claude/skills/`:

1. `grilling`: interview the user until the requirements are clear.
2. `spec-driven-development`: write the spec in `specs/<feature>.md` (every requirement gets an id like `REQ-001` and acceptance criteria), then the plan and tasks it describes.
3. `tdd`: build one task at a time, test first.
4. `verification-before-completion`: run the tests and show the output before saying anything is done.
5. `code-review-and-quality`: review the change against the spec before it is merged.

Record architecture decisions in `docs/adr/`. CI runs every test on every PR.

No code without a spec. If the spec is wrong, fix the spec first, then the code.

## Where things go

| What | Where |
|---|---|
| Specs and plans | `specs/` |
| Architecture decisions | `docs/adr/NNNN-title.md` |
| Requirement → code → test mapping | `docs/traceability.md` |
| Skill evaluation prompts and results | `evals/` |
| Development measurements (time, tokens, defects, rework) | `measurements/dev-log.csv` |
| Where each skill came from and why | `skills-vendor/VENDOR.md` |
| Changes to skills | `skills-CHANGELOG.md` |

## Stack

- Python 3.12, pytest.
- Vehicle side: Eclipse Kuksa (VSS signals), Eclipse Zenoh, Eclipse Ankaios.
- Cloud data platform: Google Pub/Sub → Dataflow (Apache Beam) → storage.
