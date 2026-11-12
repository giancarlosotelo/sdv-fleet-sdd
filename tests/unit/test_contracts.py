from pathlib import Path

import pytest

from contracts import Invalid, Valid, hazard_key, telemetry_key, validate

SAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "samples"
VALID = sorted((SAMPLES / "valid").glob("*.json"))
MALFORMED = sorted((SAMPLES / "malformed").glob("*.json"))


def test_req071_keys_per_vehicle():
    assert telemetry_key("veh-01") == "fleet/veh-01/telemetry"
    assert hazard_key("veh-02") == "fleet/veh-02/hazard"


def test_req070_valid_samples_cover_both_kinds():
    kinds = {path.name.split("_")[0] for path in VALID}

    assert kinds == {"telemetry", "hazard"}


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_req070_valid_sample_passes(path):
    result = validate(path.read_bytes())

    assert isinstance(result, Valid), result


@pytest.mark.parametrize("path", MALFORMED, ids=lambda p: p.name)
def test_req070_malformed_sample_is_rejected_with_reason(path):
    expected_in_reason = path.stem.split("__")[1]

    result = validate(path.read_bytes())

    assert isinstance(result, Invalid)
    assert expected_in_reason in result.reason.lower()


def test_req070_unknown_vehicle_is_schema_valid():
    """Fleet membership needs the config, so cloud ingest rejects it (REQ-080), not contracts."""
    assert isinstance(validate((SAMPLES / "unknown_vehicle.json").read_bytes()), Valid)
