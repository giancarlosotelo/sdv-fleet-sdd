import json
from pathlib import Path

import apache_beam as beam
from apache_beam.runners.portability.fn_api_runner import FnApiRunner
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to

from fleet.cloud.storage import SqliteStorage
from fleet.config import load_config
from fleet.pipeline.__main__ import run
from fleet.pipeline.transforms import QUARANTINE, VALID, EnrichFn, ValidateFn, read_records

ROOT = Path(__file__).resolve().parents[2]
CFG = load_config(ROOT / "config" / "fleet.yaml")
SAMPLES = ROOT / "contracts" / "samples"
HAZARD = json.loads((SAMPLES / "valid" / "hazard_veh-02_harsh_braking.json").read_text())


def test_req100_validate_splits_valid_and_quarantine_with_reason():
    records = [
        (json.dumps(HAZARD).encode(), 100),
        (b"not json", 5),
        ((SAMPLES / "unknown_vehicle.json").read_bytes(), 7),
    ]
    with TestPipeline(runner=FnApiRunner()) as p:
        out = (
            p
            | beam.Create(records)
            | beam.ParDo(ValidateFn(CFG)).with_outputs(QUARANTINE, main=VALID)
        )
        assert_that(
            out[VALID] | beam.Map(lambda r: r[0]["msg_id"]),
            equal_to([HAZARD["msg_id"]]),
            label="valid",
        )
        assert_that(
            out[QUARANTINE] | beam.Map(lambda q: (q[1].split(":")[0], q[2])),
            equal_to([("<root>", 5), ("vehicle_id", 7)]),
            label="quarantine",
        )


def test_req100_enrich_adds_name_route_and_hazard_latency():
    with TestPipeline(runner=FnApiRunner()) as p:
        out = p | beam.Create([(HAZARD, HAZARD["t0"] + 250)]) | beam.ParDo(EnrichFn(CFG))
        assert_that(
            out
            | beam.Map(
                lambda m: (m["vehicle_name"], m["route_id"], m["latency_ms"], m["received_ms"])
            ),
            equal_to([("Van 02", "B", 250, HAZARD["t0"] + 250)]),
        )


def test_req100_read_records_from_sample_dir_and_capture_file(tmp_path):
    capture = tmp_path / "capture.jsonl"
    capture.write_text(json.dumps({"received_ms": 42, "payload": json.dumps(HAZARD)}) + "\n")

    from_dir = read_records(SAMPLES)
    from_capture = read_records(capture)

    assert len(from_dir) == len(list(SAMPLES.rglob("*.json")))
    assert from_capture == [(json.dumps(HAZARD).encode(), 42)]


def test_req100_samples_produce_exact_rows(tmp_path):
    db = tmp_path / "pipeline.db"

    run(SAMPLES, db, ROOT / "config" / "fleet.yaml")

    storage = SqliteStorage(db)
    telemetry = storage.telemetry()
    alerts = storage.alerts(include_resolved=True)
    quarantine = storage.quarantine()
    assert sorted((t["vehicle_id"], t["vehicle_name"], t["route_id"]) for t in telemetry) == [
        ("veh-01", "Van 01", "A"),
        ("veh-02", "Van 02", "B"),
    ]
    assert [(a.id, a.hazard_type, a.severity, a.t1_ms - a.t0_ms) for a in alerts] == [
        (HAZARD["msg_id"], "harsh_braking", 3, 50)
    ]
    malformed = len(list((SAMPLES / "malformed").glob("*.json")))
    assert len(quarantine) == malformed + 1
    assert all(reason for _, reason, _ in quarantine)
