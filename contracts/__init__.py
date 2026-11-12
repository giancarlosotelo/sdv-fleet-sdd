import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

_SCHEMAS = Path(__file__).parent / "schemas"
VALIDATORS = {
    kind: Draft202012Validator(json.loads((_SCHEMAS / f"{kind}.json").read_text()))
    for kind in ("telemetry", "hazard")
}


@dataclass(frozen=True)
class Valid:
    msg: dict[str, Any]


@dataclass(frozen=True)
class Invalid:
    reason: str


TELEMETRY_TOPIC = "telemetry"
HAZARD_TOPIC = "hazards"
TELEMETRY_KEYS = "fleet/*/telemetry"
HAZARD_KEYS = "fleet/*/hazard"


def telemetry_key(vehicle_id: str) -> str:
    return f"fleet/{vehicle_id}/telemetry"


def hazard_key(vehicle_id: str) -> str:
    return f"fleet/{vehicle_id}/hazard"


def validate(raw: bytes | dict[str, Any]) -> Valid | Invalid:
    """Check a message against its schema; the reason starts with the offending field path."""
    try:
        msg = json.loads(raw) if isinstance(raw, bytes) else raw
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        return Invalid(f"<root>: not json: {ex}")
    if not isinstance(msg, dict):
        return Invalid(f"<root>: expected a json object, got {type(msg).__name__}")
    kind = msg.get("kind")
    if kind not in VALIDATORS:
        return Invalid(f"kind: expected one of {sorted(VALIDATORS)}, got {kind!r}")
    error = best_match(VALIDATORS[kind].iter_errors(msg))
    if error:
        where = ".".join(str(p) for p in error.absolute_path) or "<root>"
        return Invalid(f"{where}: {error.message}")
    return Valid(msg)
