# Spec: SDV Fleet Operations & Hazard Monitor

Status: APPROVED 2026-11-11
Source: `docs/product-brief.md` + grilling session 2026-11-11 (decisions Q1–Q19 recorded in §11)

## 1. Objective

A fleet operator watches three simulated battery-electric delivery vans in Oshawa, Ontario. Each van detects its own driving hazards and sends them to the cloud. Within 2 seconds, the operator sees each hazard on a live map, can acknowledge it, and can compare how safe and efficient each route is.

Success for V1: one command on a laptop runs the whole system with no infrastructure. A real-service mode (Kuksa, Zenoh, Pub/Sub emulator) passes the same end-to-end latency test in CI.

### Release scope

| | V1 (this spec) | V2 (later) |
|---|---|---|
| Simulator, rules, detector, publisher | ✅ | |
| Stand-ins for Kuksa, Zenoh, Pub/Sub | ✅ | |
| Real Kuksa, Zenoh, Pub/Sub emulator adapters + integration tests | ✅ | |
| Live cloud service: alerts, offline, trips, latency | ✅ | |
| Beam pipeline on DirectRunner (batch over captured or sample data) | ✅ | Dataflow streaming |
| Storage | ✅ SQLite | BigQuery sink |
| Live dashboard | ✅ | |
| Ankaios manifest per van (generated, structure-tested) | ✅ | Run on a GCP VM; restart test |
| CI on every PR (standin + real jobs) | ✅ | |
| GCP deployment (VM, GKE, Pub/Sub, Dataflow), auto-deploy from main | | ✅ |
| Dashboard auth | | not planned |

Requirements tagged **[V2]** are recorded but not built in V1. Everything untagged ships in V1.

## 2. Capability map

| Module id | Responsibility | Depends on |
|---|---|---|
| `config` | Fleet YAML: vans, routes, profiles, thresholds, defaults | — |
| `contracts` | JSON Schemas, Zenoh keys, shared validation. The only code shared by vehicle and cloud | — |
| `routes` | OSRM fetch, local cache, polyline geometry | config |
| `simulator` | Seeded van physics along routes, charging, trips | config, routes |
| `twin` | Kuksa interface (stand-in + real), VSS overlay | config |
| `rules` | Pure hazard rules | config |
| `detector` | Reads twin, applies rules, writes current hazard + t0 | twin, rules |
| `publisher` | Twin → Zenoh, retry/buffer | twin, contracts |
| `transport` | Zenoh + Pub/Sub interfaces (stand-in + real), Zenoh→Pub/Sub bridge | contracts |
| `storage` | Storage interface, SQLite implementation | contracts |
| `cloud` | Live service: validation, dedupe, alert lifecycle, offline, trips, latency | contracts, transport, storage, config |
| `pipeline` | Beam: validate, quarantine, enrich, write | contracts, storage, config |
| `dashboard` | FastAPI + WebSocket + Leaflet page | cloud |
| `demo` | One-command runner, flags, hazard injection, latency report | all above |
| `deploy` | Ankaios manifest generation, container images, compose, CI | config |

Build order: config, contracts → routes, rules, twin, storage, transport → simulator, detector, publisher → cloud, pipeline → dashboard → demo → deploy.

Import rule: vehicle modules (`simulator`, `twin`, `rules`, `detector`, `publisher`) and cloud modules (`cloud`, `pipeline`, `storage`, `dashboard`) never import each other. Both sides may import `contracts` and `config`.

## 3. Requirements

Each requirement has acceptance criteria (AC) written so that a test can check them.

### config

**REQ-001 Single fleet config.** Vans, routes, driving profiles, hazard thresholds, battery/charging settings, offline timeout, publisher buffer size and demo defaults all live in one YAML file.
- AC1: The default config defines `veh-01` (Van 01, route A North / Taunton Rd, 60 km/h), `veh-02` (Van 02, route B Downtown / King St, 50 km/h) and `veh-03` (Van 03, route C East / Harmony Rd, 70 km/h).
- AC2: Adding a van entry to the config (and nothing else) makes it simulate, publish, show on the dashboard and get an Ankaios manifest. Tested with a 4-van config.
- AC3: An invalid config (missing field, unknown route, duplicate id) fails at startup with an error naming the field.
- AC4: Default thresholds equal the brief's values (REQ-020).

### routes

**REQ-010 Route geometry from OSRM.** Each route in config has ≥ 2 anchor lat/lon points. At startup, any route not in the cache is fetched from the public OSRM API as a closed, road-snapped loop through its anchors.
- AC1: The fetched polyline starts and ends at the first anchor.
- AC2: The polyline is written to a gitignored cache dir, keyed by route id and a hash of the anchors. A second startup makes no network call.
- AC3: Changing a route's anchors invalidates its cache entry.

**REQ-011 Offline failure.** If a route has no cache entry and OSRM is unreachable, startup exits non-zero with an error naming the route.
- AC1: Tested with a stubbed unreachable OSRM and an empty cache.

**REQ-012 No network in tests or CI.** Unit tests and CI use committed fixture polylines and never call OSRM.
- AC1: The test suite passes with network access blocked.
- AC2: The `real` CI job also uses the committed fixtures and never calls OSRM.

### simulator

**REQ-030 Signals.** Every sim tick, each van produces position (lat/lon), speed, longitudinal acceleration, traction control active, battery SoC, coolant temperature, odometer and trip number.
- AC1: All eight signals are written to the van's twin every tick.

**REQ-031 Repeatable with a seed.** The same seed and config produce identical signal sequences in sim time.
- AC1: Two runs with seed 42 produce identical sequences for the first N sim-seconds. A different seed produces a different sequence.

**REQ-032 Time scale.** `time_scale` multiplies sim time against wall-clock time. Physics (distance, drain, trip length) runs in sim time.
- AC1: At 10×, 10 sim-seconds pass in about 1 wall-second, and the distance covered matches 1× for the same sim duration.

**REQ-033 Driving profiles.** Each route has a configured profile: stop frequency, braking intensity distribution, traction event probability and speeding tendency. Profile B (downtown) has the most stops and the highest share of harsh braking.
- AC1: With the default config and seed 42, after each van completes one full trip, route B has the highest hazards per 100 km (REQ-062).

**REQ-034 Battery and coolant.** SoC drains at a profile- and speed-dependent rate from a configured start SoC (default 60%). Coolant temperature rises with load and speed and can exceed 90 °C on demanding stretches.
- AC1: Over a long seeded run, both low-energy thresholds (20%, 10%) are crossed.

**REQ-035 Trips.** A trip is one full loop of the route. The trip number goes up when the van returns to the start.
- AC1: The trip number goes up exactly once per loop. The odometer only ever increases.

**REQ-036 Charging.** When SoC ≤ 10%, the van finishes driving to its route start, stops (speed 0), charges to 90% at the configured rate, then starts a new trip.
- AC1: SoC rises only while charging at the route start.
- AC2: Charging time isn't part of any trip. The trip after charging starts at the route start.

### twin

**REQ-040 Kuksa digital twin.** Each van's signals live in a Kuksa Databroker under standard VSS names (e.g. `Vehicle.Speed`, `Vehicle.CurrentLocation.Latitude`, `Vehicle.Powertrain.TractionBattery.StateOfCharge.Current`). Signals VSS doesn't have (trip number, traction-control-active if absent, current hazard, hazard t0, hazard severity) go in a committed custom VSS overlay.
- AC1: Every signal name used in code exists in VSS or in the overlay file.
- AC2: The stand-in and real adapters pass the same contract test suite (`standin` and `real` markers).

### rules

**REQ-020 Hazard rules.** Pure function: signals + route limit + thresholds → list of fired hazards. No I/O.

| Hazard | Fires when | Severity |
|---|---|---|
| harsh_braking | deceleration ≥ 4 m/s² | 2 high |
| harsh_braking | deceleration ≥ 7 m/s² | 3 critical |
| traction_loss | traction control active and speed ≥ 20 km/h | 3 critical |
| overheat | coolant > 90 °C | 2 high |
| low_energy | SoC ≤ 20% | 1 warning |
| low_energy | SoC ≤ 10% | 2 high |
| overspeed | speed > route limit + 10 km/h | 1 warning |

- AC1: Each row has boundary tests on both sides of the threshold (e.g. 3.99 → none, 4.0 → high, 7.0 → critical).
- AC2: A hazard type with two levels reports only its higher level.
- AC3: Changing thresholds in config changes the outcomes.

**REQ-021 Most severe wins.** When several hazards fire, the current hazard is the one with the highest severity. Ties are broken by a fixed type order in config.
- AC1: Deceleration 8 m/s² with SoC 15% gives harsh_braking critical.
- AC2: The tie-break is deterministic and tested.

### detector

**REQ-050 Detect and write back.** The detector subscribes to the van's twin signals and evaluates the rules on every update. When the current hazard changes (none→hazard, a type or severity change, or hazard→none), it writes the new current hazard, its severity and t0 (wall-clock detection time, UTC, ms) into the twin.
- AC1: Writing a 7.5 m/s² deceleration into the twin results in a twin hazard = harsh_braking, severity 3, with a t0 set.
- AC2: An unchanged hazard across ticks doesn't rewrite t0.
- AC3: Clearing all conditions writes hazard = none.

### publisher and transport

**REQ-070 Contracts.** Telemetry and hazard messages are JSON, defined by JSON Schema files in `contracts/`. Every message has `kind` (`telemetry` or `hazard`), `schema_version`, `msg_id` (UUID), `vehicle_id`, `sim_ts` and `wall_ts` (UTC epoch ms). Hazard messages add `hazard_type` (or `none`), `severity`, `t0`, `lat` and `lon`. `contracts/` also includes reproducible sample data (valid and malformed).
- AC1: The sample valid messages pass validation. Each sample malformed message fails with a named reason.
- AC2: Vehicle and cloud packages import only `contracts` and `config` from each other's world (checked by an import-lint test).

**REQ-071 Zenoh keys.** Telemetry goes to `fleet/<vehicle_id>/telemetry`. Hazard changes go to `fleet/<vehicle_id>/hazard`.
- AC1: The key builders live in `contracts` and are used by both sides.

**REQ-072 Publish rates.** Telemetry publishes at 1 Hz wall-clock per van, at any time scale. A hazard message publishes immediately on every current-hazard change, including the change to none.
- AC1: Over 10 wall-seconds, each van publishes 10 ± 1 telemetry messages, at both 1× and 10×.
- AC2: The time from a hazard change in the twin to the Zenoh put is < 100 ms in the stand-in test.

**REQ-073 Zenoh → Pub/Sub.** A bridge forwards every Zenoh message to Pub/Sub (`telemetry` and `hazards` topics) unchanged.
- AC1: The message body and `msg_id` are identical on both sides.

**REQ-074 Broker unreachable.** If Zenoh or Pub/Sub can't be reached, the publisher/bridge retries with exponential backoff. It keeps the latest hazard state plus the last N telemetry messages (N from config, default 60) and sends them on reconnect. The simulator and detector keep running. No workload crashes.
- AC1: With the transport down for 30 s and then restored, the buffered messages arrive, nothing crashes, and the oldest telemetry beyond N is dropped.
- AC2: If Kuksa is unreachable, detector and publisher retry and log without crashing.

### cloud (live service)

**REQ-080 Ingest and validate.** The service subscribes to both Pub/Sub topics and validates each message against `contracts`. Messages that fail validation or have an unknown `vehicle_id` are dropped and counted. Duplicate `msg_id`s are ignored.
- AC1: Every sample malformed message is rejected with a reason, and the service keeps running.
- AC2: A message delivered twice produces one effect.

**REQ-081 Alert lifecycle (edge-triggered).** A hazard message with a type opens an alert, stores t0, t1 and position, and resolves that van's previous open hazard alert, if any. A hazard message with `none` resolves the van's open hazard alert. An escalation (e.g. high → critical) resolves the old alert and opens a new one.
- AC1: The sequence none → high → critical → none produces 2 alerts, both resolved at the end.
- AC2: Each alert carries a single t0 (from opening) and its position at opening.

**REQ-082 Acknowledge.** The operator can acknowledge any alert. Ack stores the ack time, can't be undone, and is independent of resolved.
- AC1: An acked alert that hasn't resolved stays in the default queue.
- AC2: Acking twice keeps the first ack time.

**REQ-083 Offline detection.** A van with no telemetry for 10 wall-seconds (configurable) is marked offline and an offline alert opens. When telemetry comes back, the van is marked online and the alert resolves. Offline alerts have no latency.
- AC1: Stopping one van's telemetry opens an offline alert in 10–11 s. Resuming it resolves the alert.
- AC2: Offline time is wall-clock at any time scale.

**REQ-084 Latency.** For each hazard alert, latency = t1 (wall time the service received the message) − t0. The service reports count, median, p95 and max over all hazard alerts since startup. Target: p95 < 2 s.
- AC1: Stats on a known set of latencies match hand-computed values. The p95 method is documented and tested.

**REQ-085 Trip results.** When a van's trip number goes up, the service records the completed trip: vehicle, route, trip number, distance (odometer delta, km), energy used in kWh (sum of SoC decreases × pack capacity; SoC increases are excluded), hazard count (hazard alerts opened during the trip, escalations counted separately), and hazards per 100 km.
- AC1: A trip whose SoC series includes a rise records energy from decreases only.
- AC2: A 0 km trip doesn't divide by zero (hazards/100 km = null).

**REQ-086 Persistence.** Alerts (with ack and resolve state) and completed trips are written to storage, and alerts survive a service restart.
- AC1: Restarting with the same SQLite file shows the same alerts and ack states.

### storage

**REQ-090 Storage interface + SQLite.** One storage interface with a SQLite implementation (file path configurable, `:memory:` in tests). Tables: telemetry, alerts, trips, quarantine.
- AC1: Live service and pipeline both write through the interface, and the tests run on `:memory:`.
- AC2: **[V2]** A BigQuery implementation passes the same interface tests.

### pipeline

**REQ-100 Beam pipeline.** An Apache Beam pipeline reads telemetry and hazard messages, validates them with the shared `contracts` validation, sends malformed messages with a reason to the quarantine table, enriches valid ones with van name, route and (for hazards) latency, and writes telemetry and alerts to storage.
- AC1: Run on the sample data with the local in-process Python runner (`FnApiRunner`; Beam 2.77's DirectRunner delegates to Prism, which downloads a binary), the outputs match the expected rows exactly: N valid enriched rows, M quarantined rows with reasons.
- AC2: Each transform has unit tests using Beam's `TestPipeline` / `assert_that`.
- AC3: In V1 the pipeline runs in batch over sample data or captured messages from a demo run (`--capture` file), and from the Pub/Sub emulator in the `real` job.
- AC4: **[V2]** The same pipeline runs streaming on Dataflow.

### dashboard

**REQ-110 Live web dashboard.** FastAPI serves one static HTML/JS page (Leaflet, OSM tiles, no build step). Updates are pushed over a WebSocket.
- AC1: A hazard alert appears on a connected client within 2 s of t0 (covered by REQ-130).
- AC2: Without tile network access, routes, vans and dots still render.

**REQ-111 Map.** Shows each route polyline, each van's live position, and a dot per hazard alert at its opening position, coloured by severity: yellow warning, orange high, red critical. A van with an open hazard alert pulses red. An offline van is greyed out at its last position.
- AC1: The WebSocket messages carry everything needed to render the map (positions, severities, open/offline state), and this is verified at the message layer.
- AC2: A headless-browser smoke test checks that 3 van markers and 3 route lines render.

**REQ-112 Fleet panel.** Shows speed, battery, trip number, odometer and online/offline status per van.
- AC1: The values match the latest telemetry.

**REQ-113 Alert queue.** Newest first. Each row shows van, type, severity, time, latency (hazards only), ack state and resolved state. By default it shows unresolved alerts. A toggle also shows resolved ones. An Ack button acknowledges the alert.
- AC1: Acking from the UI persists (REQ-082) and updates all connected clients.

**REQ-114 Latency panel.** Shows median, p95 and max with a pass/fail indicator against the 2 s target.
- AC1: The values equal REQ-084's output.

**REQ-115 Route performance table.** One row per route and van: trips completed, total km, total kWh, kWh/100 km, total hazards and hazards/100 km, cumulative over completed trips only. A row stays empty until that van's first trip completes. The highest hazards/100 km row is highlighted.
- AC1: Values equal the aggregates over stored trips.

### demo

**REQ-120 One-command laptop demo.** `fleet-demo` starts all vans, the cloud service and the dashboard in one process, using stand-ins by default.
- Flags: `--port` (default 8000), `--time-scale` (10), `--seed` (42), `--config`, `--inject-hazards N`, `--real-kuksa`, `--real-zenoh`, `--real-pubsub`, `--capture FILE`.
- AC1: With the network blocked and a warm route cache, the demo starts and the dashboard serves on the port.
- AC2: Each `--real-*` flag swaps in the real adapter for that service only.

**REQ-121 Hazard injection + latency report.** `--inject-hazards N` writes N harsh-braking decelerations (≥ 7 m/s²) into the vans' twin signals, spread over time and across vans, so each one goes through detector → publisher → transport → cloud. When done, it prints count, median, p95, max and PASS/FAIL against p95 < 2 s, and exits non-zero on FAIL.
- AC1: N injections produce N hazard alerts in the report.

### quality

**REQ-130 End-to-end latency test.** A harsh-braking signal written to a van's twin results in an alert in the cloud service, and on a WebSocket client, with p95 < 2 s, using REQ-121's mechanism.
- AC1: Passes in the `standin` job.
- AC2: Passes in the `real` job (real Kuksa, Zenoh and Pub/Sub emulator).

**REQ-131 Failure-case tests.** Malformed messages (REQ-080, REQ-100), a van going offline (REQ-083), and an unreachable broker (REQ-074) each have automated tests.

**REQ-132 Test labelling.** Every test that touches an external system has the marker `standin` or `real`, and test reports show it. Real tests skip with a clear reason when their service is unreachable locally. In CI they must run and can't skip.
- AC1: A test without a marker that imports an adapter fails a collection-time check.

### deploy

**REQ-140 Ankaios manifests.** A generator produces one Ankaios manifest per van from the fleet config, with four workloads (databroker, simulator, detector, publisher) and `restartPolicy: ALWAYS`. Each workload is also a separate entrypoint with a container image definition.
- AC1: Generated manifests validate against the expected structure: one per van, four workloads each, the restart policy set and the van id passed.
- AC2: **[V2]** Under Ankaios on a GCP VM, a killed workload restarts.

**REQ-141 Local real services.** A `docker compose` file starts Kuksa Databroker, a Zenoh router and the Pub/Sub emulator for the `real` tests and the `--real-*` flags.

**REQ-142 CI.** GitHub Actions runs on every pull request. Job `standin` runs unit + standin tests, including REQ-130 AC1. Job `real` starts compose services and runs `real` tests, including REQ-130 AC2. Both must pass.
- AC1: The workflow file defines both jobs, triggered on `pull_request`.

**REQ-143 [V2] Cloud deployment.** The vans run on a GCP VM under Ankaios. The cloud service and dashboard run on GKE. The pipeline runs on Pub/Sub + Dataflow. Main auto-deploys.

## 4. Tech stack

- Python 3.12, pytest, pytest-asyncio, ruff.
- `kuksa-client` (Kuksa Databroker gRPC), `eclipse-zenoh`, `google-cloud-pubsub`, `apache-beam[gcp]`, `fastapi` + `uvicorn` (WebSocket), `jsonschema`, `pyyaml`, `httpx` (OSRM), `playwright` (one smoke test).
- Leaflet 1.9.4, vendored under `src/fleet/dashboard/static/vendor/` (changed 2026-11-11 from CDN: REQ-012 and REQ-120 AC1 need the page to work with the network blocked; only map tiles need network).
- Docker compose: `ghcr.io/eclipse-kuksa/kuksa-databroker`, `eclipse/zenoh`, `gcr.io/google.com/cloudsdktool/google-cloud-cli` (Pub/Sub emulator).
- Two environments (decided 2026-11-11): `kuksa-client` 0.6 needs protobuf ≥ 7 and `apache-beam[gcp]` needs protobuf < 7, so the Beam pipeline runs in its own venv. Pipeline tests live in `tests/pipeline/`.
- Exact versions get pinned in the plan phase. Adding any dependency beyond this list needs approval first.

## 5. Commands

```
Install main:   python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,real]"
Install pipe:   python3.12 -m venv .venv-pipeline && .venv-pipeline/bin/pip install -e ".[dev,pipeline]"
Unit+standin:   .venv/bin/pytest -m "not real" --ignore=tests/pipeline
Real services:  docker compose up -d && .venv/bin/pytest -m real --ignore=tests/pipeline
Pipeline tests: .venv-pipeline/bin/pytest tests/pipeline
Lint:           ruff check . && ruff format --check .
Demo:           fleet-demo --port 8000 --time-scale 10 --seed 42
Latency test:   fleet-demo --inject-hazards 50
Pipeline:       .venv-pipeline/bin/python -m fleet.pipeline --input contracts/samples/ --db out/fleet.db
Manifests:      python -m fleet.deploy.manifests --config config/fleet.yaml --out deploy/ankaios/
```

## 6. Project structure

```
config/fleet.yaml          → the single fleet config
contracts/                 → JSON Schemas, keys, validation, samples/ (shared package)
src/fleet/vehicle/         → simulator, twin, rules, detector, publisher
src/fleet/routes/          → OSRM fetch + cache
src/fleet/transport/       → Zenoh/PubSub interfaces, stand-ins, bridge
src/fleet/cloud/           → live service, storage
src/fleet/pipeline/        → Beam pipeline
src/fleet/dashboard/       → FastAPI app + static/
src/fleet/demo/            → CLI runner, injection, report
src/fleet/deploy/          → Ankaios manifest generator
vss/overlay.vspec          → custom VSS overlay
tests/unit/ tests/integration/ tests/e2e/ tests/fixtures/routes/
deploy/                    → Dockerfiles, compose, generated manifests
.github/workflows/ci.yml
```

## 7. Code style

```python
@dataclass(frozen=True)
class Hazard:
    type: HazardType
    severity: Severity


def evaluate(signals: Signals, limit_kmh: float, t: Thresholds) -> list[Hazard]:
    """Pure: no I/O, no clock."""
    fired = []
    if signals.decel_ms2 >= t.brake_critical_ms2:
        fired.append(Hazard(HazardType.HARSH_BRAKING, Severity.CRITICAL))
    elif signals.decel_ms2 >= t.brake_high_ms2:
        fired.append(Hazard(HazardType.HARSH_BRAKING, Severity.HIGH))
    ...
    return fired
```

- Type hints everywhere. Frozen dataclasses for values. Units go in names (`_kmh`, `_ms2`, `_pct`, `_kwh`).
- Clocks and RNG are injected, never read globally, so tests can control time and seeds.
- Adapters sit behind `Protocol` interfaces, with one stand-in and one real implementation each.
- ruff format + ruff check. Comments are rare and only for a non-obvious why.

## 8. Testing strategy

- **Unit:** rules, stats, trip/energy math, alert state machine, route cache, config validation, Beam transforms (TestPipeline), manifest generator, contract validation.
- **Integration (`standin` / `real`):** twin adapter contract suite, transport contract suite, bridge, service ingest.
- **E2E:** REQ-130, in both modes. The seeded route-B assertion (REQ-033) runs at a high time scale.
- Every REQ has at least one test, and test names reference the REQ id (e.g. `test_req020_brake_boundary`).
- Workflow per CLAUDE.md: `tdd` per task, `verification-before-completion` before claiming done.

## 9. Boundaries

- **Always:** test first; run `pytest -m "not real"` before declaring a task done; keep vehicle and cloud import-isolated; reference REQ ids in tests.
- **Ask first:** new dependencies; changing contracts/schemas; changing thresholds or timeouts away from the brief; CI config changes beyond REQ-142; anything that touches GCP.
- **Never:** deploy or write to any cloud resource; call OSRM from tests; commit the route cache or secrets; skip `real` tests in CI.

## 10. Success criteria (V1 done)

1. `pytest -m "not real"` passes with the network blocked.
2. `docker compose up -d && pytest -m real` passes.
3. `fleet-demo` starts with one command. The dashboard shows 3 moving vans, live alerts, the latency panel and, after the first trips, the route table with B highest.
4. `fleet-demo --inject-hazards 50` reports p95 < 2 s and PASS, in stand-in and in real mode.
5. Both CI jobs are green on a PR.
6. Every untagged REQ is traced to at least one passing test.

## 11. Decisions log (grilling, 2026-11-11)

| Q | Decision |
|---|---|
| Q1 | V1 = laptop demo + real-service adapters/tests + CI. GCP deploy and auto-deploy → V2 |
| Q2 | Edge-triggered alerts. Escalation opens a new alert. Auto-resolve on clear. Ack is separate |
| Q3 | Latency and offline use wall-clock time. Physics uses sim time |
| Q4–Q6 | Route geometry from OSM, fetched at startup and cached (gitignored). Fails loudly on miss + no network. Tests use fixtures |
| Q7 | Per-route driving profiles. Seeded test asserts B is highest |
| Q8 | Trip = loop. Energy in kWh from SoC decreases. Charge at route start when SoC ≤ 10%, up to 90% |
| Q9 | FastAPI + WebSocket + Leaflet, no build step |
| Q10 | Live service = 2 s path. Beam = separate consumer, batch in V1. Shared validation |
| Q11 | SQLite behind an interface. Quarantine table |
| Q12 | JSON + JSON Schema, `msg_id` dedupe, 1 Hz telemetry, hazard message on change |
| Q13 | Stand-in/real adapters, `--real-*` flags, compose, two CI jobs |
| Q14 | Ankaios manifests generated + structure-tested. Running them is V2 |
| Q15 | Latency over all hazard alerts since startup. Injection goes through the full path, PASS/FAIL exit code |
| Q16 | Public OSRM API from config anchors. Speed limits from config |
| Q17 | Route table cumulative over completed trips. Escalations count separately |
| Q18 | Retry with backoff, bounded buffer, dedupe on reconnect |
| Q19 | No auth, greyed-out offline vans, single YAML, port 8000 / 10× / seed 42 |

## 12. Open questions

1. ~~OSRM in the `real` CI job~~: resolved 2026-11-11, it uses the fixtures (REQ-012 AC2).
2. **Clock sync:** t0 (vehicle) and t1 (cloud) share a host clock in V1. In V2 (VM vs GKE), NTP skew affects latency. Out of scope for V1.
3. **OSRM terms of use:** the public demo server is fine for low-volume dev use. A V2 deployment may need a self-hosted OSRM.
