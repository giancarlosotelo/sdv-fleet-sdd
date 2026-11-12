# Plan: SDV Fleet Monitor V1

Status: APPROVED 2026-11-11
Spec: `specs/fleet-monitor.md` (APPROVED 2026-11-11). This plan never restates requirements. It refers to them by REQ id.
Tasks: `specs/fleet-monitor-tasks.md`

## 1. Approach

Build bottom-up along the capability map (spec §2). Pure logic goes first (rules, stats, trip math, alert state machine), then the stand-in adapters, then the wiring. The full system runs on stand-ins before any real service is touched. Real Kuksa, Zenoh and the Pub/Sub emulator come in late, behind the same `Protocol` interfaces and contract test suites as the stand-ins, so swapping them in is mostly adapter work.

## 2. Milestones and checkpoints

| M | Goal | Tasks | Checkpoint (gate to next milestone) |
|---|---|---|---|
| M0 | Toolchain + test harness | T01 | `pytest` green on the empty suite; marker check and import-lint check fail on a planted violation |
| M1 | Foundations (pure + storage) | T02–T07 | `pytest -m "not real"` + `ruff check .` green. REQ-001/010–012/020/021/070/071/090 covered |
| M2 | Vehicle side on stand-ins | T08–T13 | A seeded van drives a fixture route, the detector fires, and the publisher emits to the stand-in Zenoh and then the stand-in Pub/Sub (integration test) |
| M3 | Cloud side on stand-ins | T14–T18 | Sample data → service → SQLite gives the expected alerts and trips. The Beam pipeline on the samples matches expected rows |
| M4 | Dashboard + one-command demo | T19–T24 | `fleet-demo` runs locally. `fleet-demo --inject-hazards 50` prints PASS. Stand-in e2e (REQ-130 AC1) green. Route B assertion green |
| M5 | Real services | T25–T27 | `docker compose up -d && pytest -m real` green, including the real e2e (REQ-130 AC2) |
| M6 | Deploy artefacts + CI + traceability | T28–T30 | Manifests generated and tested. Both CI jobs defined. Every untagged REQ is mapped to ≥ 1 passing test |

I stop for your review at each checkpoint, with test output shown.

## 3. Dependency graph

```
T01 ─┬─ T02 config ──┬─ T05 routes ── T09 sim core ── T10 sim profiles ─┐
     ├─ T03 contracts┼─ T12 transport ── T13 publisher ─────────────────┤
     ├─ T04 rules ───┼─ T11 detector (also T08) ────────────────────────┤
     ├─ T06 storage ─┤                                                  ├─ T21 demo ─ T22 inject/e2e ─ T23 ─ T24
     ├─ T07 stats ───┼─ T14 ingest ─ T15 alerts ─ T16 offline ─ T17 ─ T19 dash srv ─ T20 page ─┘
     │               └─ T18 pipeline
     └─ T08 twin
M5: T25 (after T08, T22) ─ T26 (after T12) ─ T27
M6: T28 (after T02) ─ T29 (after T27) ─ T30
```

## 4. Parallel vs sequential

- **Parallel:** in M1, T02–T07 touch disjoint files. In M2/M3, the vehicle track (T08–T13) and cloud track (T14–T18) touch disjoint packages because of the import rule.
- **Sequential:** M4 wires everything, so it runs strictly in order. M5 is sequential because the adapters share the compose file.
- Default is to work inline, one task at a time. Parallel writers only if you ask, per your delegation rules.

## 5. Key design choices (implementation-level, within the spec)

- **Async core:** one `asyncio` loop in the demo. Each van's simulator, detector and publisher are tasks. Clock and RNG are injected (spec §7), and a `FakeClock` drives the unit tests.
- **Stand-ins:** an in-memory pub/sub bus with key-pattern matching (`fleet/*/hazard`) for Zenoh, a per-topic asyncio queue for Pub/Sub, and a dict plus subscriber callbacks for Kuksa.
- **Alert state machine:** a pure function `(state, message) → (state, events)`, unit-tested on its own. The service wraps it with I/O.
- **p95 method:** nearest-rank on the sorted latencies (documented in code and test, REQ-084 AC1).
- **Route fixtures:** generated once by a script that calls OSRM, then committed under `tests/fixtures/routes/`. The script is the only code allowed to hit OSRM outside the runtime cache path.
- **Seeded route-B test:** runs the sim, detector and stand-ins in-process with a fake clock at maximum speed, so it doesn't depend on wall time.

## 6. Pinned versions (latest on PyPI, 2026-11-11)

| Package | Version |
|---|---|
| python | 3.12 |
| kuksa-client | 0.6.0 |
| eclipse-zenoh | 1.10.2 |
| google-cloud-pubsub | 2.43.0 |
| apache-beam[gcp] | 2.77.0 |
| fastapi | 0.162.5 |
| uvicorn[standard] | 0.54.0 |
| jsonschema | 4.26.0 |
| pyyaml | 6.0.3 |
| httpx | 0.28.1 |
| playwright | 1.65.1 |
| pytest / pytest-asyncio | 9.2.0 / latest compatible |
| ruff | 0.17.4 |

**Two environments** (decided 2026-11-11 after T01): `kuksa-client 0.6.0` needs protobuf ≥ 7.35.1, while `apache-beam[gcp] 2.77.0` needs < 7 (and its bigtable dependency ≥ 6.33). `kuksa-client 0.5.2` pins < 6, so no single environment works. `.venv` = `.[dev,real]` for everything except the pipeline. `.venv-pipeline` = `.[dev,pipeline]` for `fleet.pipeline` and `tests/pipeline/`. The main venv runs with `--ignore=tests/pipeline`, an explicit exclusion rather than a skip. `fleet.pipeline` shares only `contracts`, `config` and `fleet.cloud.storage` with the rest, all of which run on core deps.

Leaflet 1.9.4 from cdnjs. Docker images get pinned by tag in T25. `pytest-asyncio` approved 2026-11-11 and added to spec §4.

## 7. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Python 3.12 wasn't installed | Blocked T01 | Resolved: you are installing 3.12 (2026-11-11) |
| apache-beam is heavy and its wheels are slow on macOS arm64 | Slow installs/CI | Beam lives only in `.venv-pipeline`. CI caches pip per venv |
| protobuf conflict between kuksa-client and Beam | Can't share one env | Resolved: two venvs (see §6) |
| kuksa-client 0.6 / zenoh 1.x API differences from docs | Adapter rework | The real adapters are thin and the contract suite pins behaviour. Spike them in T25/T26 first |
| Route-B assertion is fragile to profile tuning | Flaky REQ-033 | Fixed seed and fake clock. Tune profiles with a margin (B ≥ 1.5× next) so small changes don't flip it |
| Real e2e p95 < 2 s on CI runners | Flaky REQ-130 AC2 | Adapters push (no polling). Warm-up before measuring. Report the full distribution on fail. I don't raise the target |
| Pub/Sub emulator image is large and starts slowly | Slow `real` job | Compose healthchecks plus a wait step |
| OSRM public server rate limit or downtime | Only the fixture script and first runs | Fixtures are committed once. Runtime cache keyed per route |
| Playwright browsers in CI | Extra setup | `playwright install --with-deps chromium` in the standin job only |

## 8. Out of plan (V2, per spec)

REQ-090 AC2, REQ-100 AC4, REQ-140 AC2, REQ-143.
