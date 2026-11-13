# MVP vs V1 (SDD): comparison

Two builds of the same product, the SDV Fleet Operations & Hazard Monitor:

- **MVP**: [`sdv-fleet-monitor`](https://github.com/mohammad-dabash22/sdv-fleet-monitor), built by the group with AI help and no spec process.
- **V1**: this repo, built from scratch by Claude Code following spec-driven development with five vendored skills: `grilling`, `spec-driven-development`, `tdd`, `verification-before-completion` and `code-review-and-quality`. It started from a product brief only, with no access to the MVP code.

Numbers measured on 2026-11-11 on the same laptop, unless marked as reported.

## Summary

| | MVP | V1 (SDD) |
|---|---|---|
| How it was built | 3 people, 34 commits, Oct 18 – Nov 1 | 1 agent session, 3 commits, Nov 11 |
| Requirements | Charter and SRS written once and never updated; 4 FR ids appear in code | 44 REQs with acceptance criteria (43 in V1, 1 tagged V2), updated as decisions changed |
| Traceability | None enforced | `tests/test_traceability.py` fails if any V1 REQ has no test |
| Tests | 34, all passing in 1 s | 231: 221 passed, 10 skipped (need Docker) in 45 s; plus 4 pipeline tests in a separate venv |
| Mocked vs real tests | Not distinguished | Every test is marked `standin` or `real`; in CI, real tests fail instead of skipping |
| Pub/Sub + Beam/Dataflow | Not built | Pub/Sub (emulator), Beam pipeline on the DirectRunner, schemas, malformed samples, quarantine |
| Storage | PostgreSQL on GKE | SQLite behind an interface (BigQuery is V2) |
| Deployment | Live on GCP: vans on a VM under Ankaios, cloud on GKE, Jenkins auto-deploy | Local only: Docker Compose and a Dockerfile; Ankaios manifests generated and structure-tested but not run; GCP is V2 |
| CI | GitHub Actions (tests) + Jenkins (deploy), both ran | GitHub Actions with a stand-in job and a real-services job, never run (not pushed) |
| Latency, hazard to alert | Reported: median 58 ms, p95 64 ms, VM → GKE over Zenoh | Measured stand-in run: p95 1 ms, PASS. Reported real-services run: p95 55 ms, local |

The two products are not the same scope. MVP went further on deployment; V1 went further on the data pipeline, tests and traceability. The rest of this report explains the difference that matters for the course: how much the spec controlled the output.

## 1. Requirements and how they changed

**MVP.** From the group's notes on how the MVP got built:
- The charter, SRS and plan were written once and never re-read.
- The SRS still names GitHub Actions for deployment (Jenkins does it) and Velocitas (rejected).
- Alert acknowledgement was built, tested and demonstrated but traces to no requirement.
- The AI chose the CI/CD tool, the deployment strategy and the infrastructure naming on its own.

**V1.**
- `grilling` asked 19 questions one at a time. Each answer is in the spec's decisions log (§11). Two of my answers overrode its recommendations:
  - Q4: use OpenStreetMap routes, not hand-picked waypoints.
  - Q5: fetch routes at startup instead of committing them at build time.
- `spec-driven-development` turned the answers into:
  - `specs/fleet-monitor.md`: 44 REQs, a V1/V2 scope table, success criteria;
  - a plan;
  - 30 tasks in 6 milestones.
- When the build proved the spec wrong, the spec was changed first, and the dev log records each amendment:
  - REQ-070 gained a `kind` field;
  - REQ-100 AC1 now pins Beam's FnApiRunner;
  - REQ-012 and REQ-120 now require Leaflet to be vendored so the dashboard works offline.
- The things the AI decided on its own in the MVP were decisions I made during grilling in V1: scope, storage, transport flags, CI shape. All of them are in the decisions log.

## 2. Verification

| | MVP | V1 |
|---|---|---|
| Test functions | 34 | 168 test functions (231 cases with parametrization) |
| Unit / integration / end-to-end | Mixed, unlabelled | `tests/unit`, `tests/integration`, `tests/e2e`, `tests/pipeline` |
| Failure cases | Few | Malformed messages (12 samples), van offline, broker outage with retry and backoff, Pub/Sub outage |
| Network | Allowed | Blocked for the whole suite; the routes come from fixtures |
| Test quality checks | None | Mutation checks found tests that passed for the wrong reason (dev log T02, T04) |
| Evidence before "done" | None | `verification-before-completion`: the final row of the dev log lists the commands run and their results |

**Defects the process caught before they shipped** (from `measurements/dev-log.csv`):
- **kuksa-client vs Beam:** they need incompatible protobuf versions. Found by a dry-run install at verification. The fix was two venvs, written into the spec and the CI.
- **Stand-in vs real Kuksa:** the stand-in batched updates, but real Kuksa notifies once per signal, so in real mode the publisher crashed and sent zero hazards. Only the real-services contract test caught it. The stand-in was fixed to match.
- **Beam runner:** the DirectRunner silently handed off to Prism, which downloads a binary. The runner is now pinned and the spec amended.
- **Dashboard and demo:** missing hazard dots after a page reload; injection waiting on the wrong condition (49 s down to 11 s); a CDN dependency that broke offline mode.

**The review:**
- `code-review-and-quality` ran after the build, and its findings were fixed in commit `e1a72f9`: 23 files, +502/−97, about half of it new tests.
- Areas fixed: the alert lifecycle, restoring a van after offline, Kuksa and Pub/Sub resilience, the injection report, and test labels.
- In the MVP, PRs #2 and #4 were merged with zero review comments.

## 3. What V1 didn't do (honest gaps)

- **No GCP deployment.** Deploying the vans to a VM, the cloud to GKE, Dataflow streaming and BigQuery are all tagged V2 in the spec. Here the MVP is ahead.
- **CI never ran.** The workflow exists but the repo isn't pushed, so success criterion 5 (both CI jobs green) is not met.
- **Real-services tests not re-run.** I did not start Docker for this report. The dev log says they passed and the 10 skipped tests print the command to run them. To check: `docker compose -f deploy/compose.yaml up -d && .venv/bin/pytest -m real`.
- **Token usage not captured.** Every dev log row says "fill from /cost", so the token comparison the rubric asks for is missing for V1. Fill it in before the report.
- **The comparison isn't like for like.** The MVP spent two weeks of three people's time largely on live GCP infrastructure. V1 is one agent session that stopped at the laptop and CI. Compare process and quality, not speed.
- **Stand-in latency proves nothing.** The 1 ms p95 is all in-process. Only the real-services run (55 ms, local) and the MVP's GCP run (64 ms) measure a real network, and those two environments differ.

## 4. What the skills contributed

| Skill | Observable effect in V1 | Limitation seen |
|---|---|---|
| `grilling` | 19 decisions captured before any code; my overrides recorded with reasons | Long (25 min); it asks about things the brief already answered |
| `spec-driven-development` | REQ ids, acceptance criteria, scope table, plan, tasks; spec amended when wrong | Ignored its own default locations (`tasks/`) in favour of CLAUDE.md; the separate capability-map gate was folded into the spec |
| `tdd` | 168 tests; mutation checks; every task test-first | Validation code was written ahead of its tests once (T02); tests were back-filled |
| `verification-before-completion` | No "done" without command output; caught the protobuf conflict | Can only verify what it can run: no Docker in CI, no GCP |
| `code-review-and-quality` | One review pass, 23 files fixed | One pass at the end, not per task; it reviewed its own author's work in the same session |

## 5. Changes to consider for V2 (customized skills)

Each one comes from a gap above:

1. **`spec-driven-development`:** make the traceability test part of the skill, not something the agent happened to add in T30. It fails when a REQ has no test.
2. **`code-review-and-quality`:** review each milestone, run by a fresh agent that didn't write the code (independent verification).
3. **`verification-before-completion`:** require `pytest -m real` against Docker, and a pushed CI run, before "done".
4. **`grilling`:** read the brief first and only ask about what it leaves open, to cut the 25 minutes.
5. **Measurement:** a step at the end of each task that records `/cost` tokens in the dev log, so V1 and V2 can be compared on cost.
6. **Deployment scope:** add the GCP deployment as V2 requirements so the spec drives it, unlike the MVP's hand-clicked Jenkins setup.

## How to reproduce

```bash
# MVP (its own repo)
.venv/bin/python -m pytest                                    # 34 passed

# V1 (this repo; setup in README.md)
.venv/bin/pytest --ignore=tests/pipeline -rs                  # 221 passed, 10 skipped
.venv-pipeline/bin/pytest tests/pipeline -m "not real"        # 4 passed
.venv/bin/fleet-demo --inject-hazards 50 --port 8765          # p95 1 ms, PASS (stand-ins)
docker compose -f deploy/compose.yaml up -d && .venv/bin/pytest -m real --ignore=tests/pipeline
```
