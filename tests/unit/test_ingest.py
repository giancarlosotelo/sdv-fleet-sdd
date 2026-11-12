from pathlib import Path

import pytest

from contracts import Invalid, Valid
from fleet.cloud.ingest import DUPLICATE, Ingest

SAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "samples"


@pytest.fixture
def ingest():
    return Ingest({"veh-01", "veh-02", "veh-03"})


@pytest.mark.parametrize(
    "path", sorted((SAMPLES / "malformed").glob("*.json")), ids=lambda p: p.name
)
def test_req080_malformed_is_rejected_and_counted(ingest, path):
    result = ingest.check(path.read_bytes())

    assert isinstance(result, Invalid)
    assert ingest.rejected == 1


def test_req080_unknown_vehicle_is_rejected(ingest):
    result = ingest.check((SAMPLES / "unknown_vehicle.json").read_bytes())

    assert isinstance(result, Invalid)
    assert "veh-99" in result.reason


def test_req080_valid_message_accepted(ingest):
    raw = (SAMPLES / "valid" / "telemetry_veh-01.json").read_bytes()

    assert isinstance(ingest.check(raw), Valid)


def test_req080_duplicate_msg_id_ignored(ingest):
    raw = (SAMPLES / "valid" / "hazard_veh-02_harsh_braking.json").read_bytes()

    assert isinstance(ingest.check(raw), Valid)
    assert ingest.check(raw) is DUPLICATE
    assert ingest.rejected == 0
