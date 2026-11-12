# Tasks: SDV Fleet Monitor V1

Status: APPROVED 2026-11-11
Spec: `specs/fleet-monitor.md` · Plan: `specs/fleet-monitor-plan.md`

Each task is built test-first (`tdd`), touches ≤ ~5 source files plus its tests, and ends with `verification-before-completion`. Default verification for every task: `.venv/bin/pytest -m "not real" --ignore=tests/pipeline && ruff check . && ruff format --check .` all green (and `.venv-pipeline/bin/pytest tests/pipeline` for pipeline tasks), plus the task's specific check below.

## M0 Toolchain

- [x] **T01 Project skeleton + test harness**. REQ-132, REQ-070 AC2
  - Acceptance: `pyproject.toml` with pinned deps and extras (`dev`, `pipeline`, `real`). pytest config registers the `standin` and `real` markers. A collection hook fails any test that imports an adapter without a marker. An import-lint test fails if `fleet.vehicle` imports `fleet.cloud`/`pipeline`/`dashboard` or the reverse.
  - Verify: harness green on the empty suite. A planted unmarked adapter test and a planted cross-import each fail (shown, then removed).
  - Files: `pyproject.toml`, `conftest.py`, `tests/test_harness.py`, `tests/test_import_isolation.py`, `.gitignore`

## M1 Foundations

- [x] **T02 Fleet config**. REQ-001 AC1, AC3, AC4
  - Acceptance: `config/fleet.yaml` holds the 3 vans, their routes (OSRM anchors), profiles, brief thresholds, battery, charging, offline, buffer and demo defaults. The loader returns typed frozen dataclasses and rejects a missing field, unknown route or duplicate id with an error naming the field.
  - Verify: `pytest tests/unit/test_config.py`
  - Files: `config/fleet.yaml`, `src/fleet/config.py`, `tests/unit/test_config.py`

- [x] **T03 Contracts**. REQ-070, REQ-071
  - Acceptance: JSON Schemas for telemetry and hazard, `validate(msg) → ok | reason`, key builders, plus `samples/valid/*.json` and `samples/malformed/*.json`, with one file per malformation (missing field, bad type, bad version, unknown vehicle, not JSON).
  - Verify: `pytest tests/unit/test_contracts.py`. Every sample is classified as expected.
  - Files: `contracts/schemas/*.json`, `contracts/__init__.py`, `contracts/samples/**`, `tests/unit/test_contracts.py`

- [x] **T04 Hazard rules**. REQ-020, REQ-021
  - Acceptance: a pure `evaluate()` and `most_severe()`. Boundary tests on both sides of every threshold. Thresholds come from config. Deterministic tie-break.
  - Verify: `pytest tests/unit/test_rules.py`
  - Files: `src/fleet/vehicle/rules.py`, `tests/unit/test_rules.py`

- [x] **T05 Routes: OSRM fetch + cache + fixtures**. REQ-010, REQ-011, REQ-012
  - Acceptance: fetches a closed loop through the anchors and caches it under `.cache/routes/<route>-<anchorhash>.json` (gitignored). A cache hit makes no HTTP call. A miss with OSRM unreachable exits non-zero naming the route. `scripts/gen_route_fixtures.py` writes `tests/fixtures/routes/` (run once, output committed).
  - Verify: `pytest tests/unit/test_routes.py` with `httpx` mocked. The full suite passes with the network blocked (socket guard in conftest).
  - Files: `src/fleet/routes/osrm.py`, `src/fleet/routes/cache.py`, `scripts/gen_route_fixtures.py`, `tests/fixtures/routes/*.json`, `tests/unit/test_routes.py`

- [x] **T06 Storage**. REQ-090 AC1
  - Acceptance: a `Storage` Protocol and SQLite implementation with telemetry, alerts, trips and quarantine tables. Works on `:memory:` and on a file.
  - Verify: `pytest tests/unit/test_storage.py`
  - Files: `src/fleet/cloud/storage.py`, `tests/unit/test_storage.py`

- [x] **T07 Pure analytics**. REQ-084 AC1, REQ-085 AC1, AC2
  - Acceptance: `latency_stats()` (count, median, nearest-rank p95, max), `energy_used_kwh()` (decreases only), `hazards_per_100km()` (null for 0 km).
  - Verify: `pytest tests/unit/test_analytics.py`. The checks are against hand-computed values.
  - Files: `src/fleet/cloud/analytics.py`, `tests/unit/test_analytics.py`

## M2 Vehicle side (stand-ins)

- [x] **T08 Twin: interface, stand-in, VSS overlay**. REQ-040
  - Acceptance: a `Twin` Protocol (get, set, subscribe), an in-memory stand-in and `vss/overlay.vspec`. A shared contract suite runs against the stand-in (`standin`). A test checks that every signal name used in code exists in VSS or the overlay.
  - Verify: `pytest tests/integration/test_twin_contract.py -m standin`
  - Files: `src/fleet/vehicle/twin.py`, `src/fleet/vehicle/signals.py`, `vss/overlay.vspec`, `tests/integration/test_twin_contract.py`

- [x] **T09 Simulator core**. REQ-030, REQ-031, REQ-032
  - Acceptance: moves along the fixture polyline, writes all 8 signals each tick, gives identical output for the same seed, and scales time with no change in sim-time distance.
  - Verify: `pytest tests/unit/test_simulator.py`
  - Files: `src/fleet/vehicle/simulator.py`, `tests/unit/test_simulator.py`

- [x] **T10 Simulator profiles, battery, coolant, trips, charging**. REQ-033 (profiles), REQ-034, REQ-035, REQ-036
  - Acceptance: profiles come from config. The trip counter goes up once per loop. SoC drains and charges only at the route start, from ≤ 10% to 90%. A long seeded run crosses 20% and 10%.
  - Verify: `pytest tests/unit/test_simulator_profiles.py`
  - Files: `src/fleet/vehicle/simulator.py`, `src/fleet/vehicle/profiles.py`, `tests/unit/test_simulator_profiles.py`

- [x] **T11 Detector**. REQ-050
  - Acceptance: subscribes to the twin and writes hazard, severity and t0 only on change. t0 comes from the injected wall clock.
  - Verify: `pytest tests/unit/test_detector.py` (twin stand-in, fake clock)
  - Files: `src/fleet/vehicle/detector.py`, `tests/unit/test_detector.py`

- [x] **T12 Transport interfaces, stand-ins, bridge**. REQ-071, REQ-073
  - Acceptance: `Zenoh` and `PubSub` Protocols, in-memory stand-ins, and a Zenoh→Pub/Sub bridge that keeps the body and msg_id unchanged. A contract suite runs against the stand-ins.
  - Verify: `pytest tests/integration/test_transport_contract.py -m standin`
  - Files: `src/fleet/transport/zenoh.py`, `src/fleet/transport/pubsub.py`, `src/fleet/transport/bridge.py`, `tests/integration/test_transport_contract.py`

- [x] **T13 Publisher: rates, hazard-on-change, retry and buffer**. REQ-072, REQ-074
  - Acceptance: 1 Hz telemetry on the wall clock at 1× and 10×. Hazard messages go out immediately, including none. Exponential backoff. The buffer keeps the last N telemetry messages plus the latest hazard state. Nothing crashes when the broker or Kuksa is down.
  - Verify: `pytest tests/unit/test_publisher.py` (fake clock, a flaky stand-in transport)
  - Files: `src/fleet/vehicle/publisher.py`, `tests/unit/test_publisher.py`

## M3 Cloud side (stand-ins)

- [x] **T14 Ingest: validate, reject, dedupe**. REQ-080
  - Acceptance: subscribes to both topics, drops and counts malformed or unknown-vehicle messages with a reason, and ignores a duplicate msg_id.
  - Verify: `pytest tests/unit/test_ingest.py` using the contract samples
  - Files: `src/fleet/cloud/ingest.py`, `tests/unit/test_ingest.py`

- [x] **T15 Alert state machine, ack, persistence**. REQ-081, REQ-082, REQ-086
  - Acceptance: pure transitions (none→high→critical→none gives 2 alerts, both resolved). Ack is idempotent and keeps the first time. Alerts survive a restart on a file DB.
  - Verify: `pytest tests/unit/test_alerts.py`
  - Files: `src/fleet/cloud/alerts.py`, `tests/unit/test_alerts.py`

- [x] **T16 Offline detection**. REQ-083
  - Acceptance: 10 s wall-clock silence (configurable) opens an offline alert. Telemetry coming back resolves it. Wall time applies at any time scale.
  - Verify: `pytest tests/unit/test_offline.py` (fake clock)
  - Files: `src/fleet/cloud/offline.py`, `tests/unit/test_offline.py`

- [x] **T17 Service: latency + trip recording**. REQ-084, REQ-085, plus wiring of T14–T16
  - Acceptance: t1 is stamped at receipt and stats are exposed. A trip-number increment records a trip row with distance, kWh, hazards and hazards/100 km.
  - Verify: `pytest tests/integration/test_service.py -m standin`. Feeding the sample stream gives the expected alerts and trips in SQLite.
  - Files: `src/fleet/cloud/service.py`, `src/fleet/cloud/trips.py`, `tests/integration/test_service.py`

- [x] **T18 Beam pipeline**. REQ-100 AC1–AC3 (file input)
  - Acceptance: validate → quarantine with reason → enrich (name, route, latency) → write. Unit tests per transform with `TestPipeline`. Run on the samples, it matches the expected rows exactly.
  - Setup: create `.venv-pipeline` with `.[dev,pipeline]` (plan §6), and add it to `.gitignore`.
  - Verify: `.venv-pipeline/bin/pytest tests/pipeline` and `.venv-pipeline/bin/python -m fleet.pipeline --input contracts/samples/ --db out/test.db`
  - Files: `src/fleet/pipeline/__main__.py`, `src/fleet/pipeline/transforms.py`, `tests/pipeline/test_pipeline.py`

## M4 Dashboard + demo

- [x] **T19 Dashboard server**. REQ-110 AC1 (message layer), REQ-111 AC1, REQ-112–REQ-115, REQ-082 via the UI
  - Acceptance: FastAPI app. The WebSocket pushes snapshot + delta messages (positions, fleet panel, alerts, latency, route table). An ack endpoint reaches all clients.
  - Verify: `pytest tests/unit/test_dashboard_api.py` (FastAPI TestClient WS)
  - Files: `src/fleet/dashboard/app.py`, `src/fleet/dashboard/messages.py`, `tests/unit/test_dashboard_api.py`

- [x] **T20 Dashboard page**. REQ-110 AC2, REQ-111 AC2, REQ-113 UI
  - Acceptance: one static page with Leaflet. Routes, van markers, severity-coloured dots, red pulse, grey offline vans, the 4 panels, a resolved toggle and an Ack button.
  - Verify: `pytest tests/e2e/test_dashboard_smoke.py -m standin` (Playwright: 3 markers + 3 routes render, tiles blocked)
  - Files: `src/fleet/dashboard/static/index.html`, `src/fleet/dashboard/static/app.js`, `src/fleet/dashboard/static/app.css`, `tests/e2e/test_dashboard_smoke.py`

- [x] **T21 Demo runner**. REQ-120
  - Acceptance: the `fleet-demo` entrypoint wires every van, the bridge, the service and the dashboard on stand-ins, with every flag listed in the spec. `--capture` writes the message stream to a file.
  - Verify: `pytest tests/integration/test_demo_startup.py -m standin` (starts, serves `/`, shuts down). Then a manual `fleet-demo` run with a screenshot or log shown.
  - Files: `src/fleet/demo/__main__.py`, `src/fleet/demo/wiring.py`, `tests/integration/test_demo_startup.py`

- [x] **T22 Hazard injection, latency report, stand-in e2e**. REQ-121, REQ-130 AC1
  - Acceptance: N injected decelerations give N alerts. The report shows count, median, p95, max and PASS/FAIL, and exits non-zero on FAIL. The e2e asserts p95 < 2 s, measured at the cloud and at a WS client.
  - Verify: `pytest tests/e2e/test_latency.py -m standin` and `fleet-demo --inject-hazards 50` → PASS
  - Files: `src/fleet/demo/inject.py`, `src/fleet/demo/report.py`, `tests/e2e/test_latency.py`

- [x] **T23 Fleet-shape tests: route B + 4-van config**. REQ-033 AC1, REQ-001 AC2 (sim/publish/dashboard part)
  - Acceptance: with seed 42 and one trip per van, B has the highest hazards/100 km. A 4-van test config simulates, publishes and appears in the WS snapshot.
  - Verify: `pytest tests/e2e/test_fleet_shape.py -m standin`
  - Files: `tests/e2e/test_fleet_shape.py`, `tests/fixtures/fleet-4vans.yaml`, profile tuning in `config/fleet.yaml`

- [x] **T24 Failure-case sweep**. REQ-131, REQ-074 AC1/AC2, REQ-083 AC1, REQ-080 AC1
  - Acceptance: end-to-end on stand-ins with malformed messages injected, one van's telemetry stopped and restarted, and the transport down for 30 s and then restored. The service and vans survive, the alerts are as specified, and the buffer drains.
  - Verify: `pytest tests/e2e/test_failures.py -m standin`
  - Files: `tests/e2e/test_failures.py`

## M5 Real services

- [x] **T25 Compose + real Kuksa adapter**. REQ-141, REQ-040 AC2
  - Acceptance: `deploy/compose.yaml` runs databroker (with the overlay loaded), Zenoh router and Pub/Sub emulator, with healthchecks and pinned image tags. The real Kuksa adapter passes the twin contract suite.
  - Verify: `docker compose -f deploy/compose.yaml up -d && pytest tests/integration/test_twin_contract.py -m real`
  - Files: `deploy/compose.yaml`, `src/fleet/vehicle/twin_kuksa.py`, `tests/integration/test_twin_contract.py` (param)

- [x] **T26 Real Zenoh + Pub/Sub emulator adapters**. REQ-071/073 (real), REQ-120 AC2
  - Acceptance: both pass the transport contract suite against compose. The `--real-zenoh` / `--real-pubsub` / `--real-kuksa` flags each swap only that adapter.
  - Verify: `pytest tests/integration/test_transport_contract.py -m real`
  - Files: `src/fleet/transport/zenoh_real.py`, `src/fleet/transport/pubsub_real.py`, `src/fleet/demo/wiring.py`

- [x] **T27 Real e2e + pipeline from emulator**. REQ-130 AC2, REQ-100 AC3 (emulator input)
  - Acceptance: the latency e2e passes with all three real services and p95 < 2 s. The pipeline reads from an emulator subscription and writes the expected rows.
  - Verify: `.venv/bin/pytest tests/e2e/test_latency.py -m real` and `.venv-pipeline/bin/pytest tests/pipeline/test_pipeline_emulator.py -m real`
  - Files: `tests/e2e/test_latency.py` (param), `src/fleet/pipeline/__main__.py` (source option), `tests/pipeline/test_pipeline_emulator.py`

## M6 Deploy, CI, traceability

- [x] **T28 Workload entrypoints, Dockerfiles, Ankaios manifests**. REQ-140 AC1, REQ-001 AC2 (manifest part)
  - Acceptance: separate entrypoints for simulator, detector and publisher. One Dockerfile with per-workload commands. The generator writes one manifest per van with 4 workloads, `restartPolicy: ALWAYS` and the van id passed. The 4-van config gives 4 manifests.
  - Verify: `pytest tests/unit/test_manifests.py` and `python -m fleet.deploy.manifests --config config/fleet.yaml --out deploy/ankaios/`
  - Files: `src/fleet/deploy/manifests.py`, `src/fleet/vehicle/__main__.py`, `deploy/Dockerfile`, `tests/unit/test_manifests.py`

- [x] **T29 CI workflow**. REQ-142
  - Acceptance: `.github/workflows/ci.yml` runs on `pull_request` with jobs `standin` (main venv: unit + standin + Playwright; pipeline venv: `tests/pipeline -m "not real"`) and `real` (compose up; main venv `pytest -m real --ignore=tests/pipeline`; pipeline venv `pytest tests/pipeline -m real`; real tests can't skip there). Each venv's pip cache is keyed separately.
  - Verify: a structure test on the YAML, plus `act` or a push to a PR branch when you say so. I don't push.
  - Files: `.github/workflows/ci.yml`, `tests/unit/test_ci_config.py`

- [x] **T30 Traceability check**. Spec §10 item 6
  - Acceptance: a test collects REQ ids from the spec (untagged ones only) and from test names and docstrings, and fails if any V1 REQ has no test.
  - Verify: `pytest tests/test_traceability.py` green. Full `pytest -m "not real"` and `pytest -m real` outputs shown.
  - Files: `tests/test_traceability.py`
