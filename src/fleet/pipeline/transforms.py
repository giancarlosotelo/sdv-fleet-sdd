"""Beam transforms: validate -> quarantine | enrich -> write (spec REQ-100)."""

import json
from pathlib import Path
from typing import Any

import apache_beam as beam

from contracts import Invalid, validate
from fleet.cloud.storage import Alert, SqliteStorage
from fleet.config import FleetConfig

VALID = "valid"
QUARANTINE = "quarantine"
Record = tuple[bytes, int]  # raw message, received_ms


def read_records(source: Path) -> list[Record]:
    """A capture file (JSONL of received_ms + payload) or a directory of one-message JSON files.

    Files carry no receipt time, so their wall_ts stands in for it.
    """
    if source.is_file():
        rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        return [(r["payload"].encode(), r["received_ms"]) for r in rows]
    records = []
    for path in sorted(source.rglob("*.json")):
        raw = path.read_bytes()
        try:
            received_ms = int(json.loads(raw).get("wall_ts", 0))
        except (ValueError, AttributeError, TypeError):
            received_ms = 0
        records.append((raw, received_ms))
    return records


def read_pubsub(subscription: str, batch: int = 500) -> list[Record]:
    """Drains a Pub/Sub subscription (the emulator in V1); publish time stands in for receipt."""
    from google.cloud import pubsub_v1

    subscriber = pubsub_v1.SubscriberClient()
    records: list[Record] = []
    while True:
        response = subscriber.pull(subscription=subscription, max_messages=batch, timeout=10)
        if not response.received_messages:
            return records
        for received in response.received_messages:
            published = received.message.publish_time
            records.append((received.message.data, int(published.timestamp() * 1000)))
        subscriber.acknowledge(
            subscription=subscription, ack_ids=[r.ack_id for r in response.received_messages]
        )


class ValidateFn(beam.DoFn):
    def __init__(self, cfg: FleetConfig):
        self._known = {v.id for v in cfg.vehicles}

    def process(self, record: Record):
        raw, received_ms = record
        result = validate(raw)
        if not isinstance(result, Invalid) and result.msg["vehicle_id"] not in self._known:
            result = Invalid(f"vehicle_id: unknown vehicle {result.msg['vehicle_id']!r}")
        if isinstance(result, Invalid):
            yield beam.pvalue.TaggedOutput(QUARANTINE, (raw, result.reason, received_ms))
        else:
            yield result.msg, received_ms


class EnrichFn(beam.DoFn):
    def __init__(self, cfg: FleetConfig):
        self._vans = {v.id: (v.name, v.route.id) for v in cfg.vehicles}

    def process(self, item: tuple[dict[str, Any], int]):
        msg, received_ms = item
        name, route_id = self._vans[msg["vehicle_id"]]
        enriched = msg | {"vehicle_name": name, "route_id": route_id, "received_ms": received_ms}
        if msg["kind"] == "hazard":
            enriched["latency_ms"] = received_ms - msg["t0"]
        yield enriched


class WriteFn(beam.DoFn):
    """Telemetry rows, one alert row per detected hazard (clears are not alerts), quarantine rows."""

    def __init__(self, db: str):
        self._db = db

    def setup(self):
        self._storage = SqliteStorage(self._db)

    def teardown(self):
        self._storage.close()

    def process(self, msg: dict[str, Any]):
        if msg["kind"] == "telemetry":
            core = {k: v for k, v in msg.items() if k not in ("vehicle_name", "route_id")}
            self._storage.add_telemetry(core, msg["vehicle_name"], msg["route_id"])
        elif msg["hazard_type"] != "none":
            self._storage.save_alert(
                Alert(
                    id=msg["msg_id"],
                    vehicle_id=msg["vehicle_id"],
                    kind="hazard",
                    hazard_type=msg["hazard_type"],
                    severity=msg["severity"],
                    t0_ms=msg["t0"],
                    t1_ms=msg["received_ms"],
                    lat=msg["lat"],
                    lon=msg["lon"],
                    opened_ms=msg["received_ms"],
                    resolved_ms=None,
                    acked_ms=None,
                    trip=None,
                )
            )


class WriteQuarantineFn(WriteFn):
    def process(self, item: tuple[bytes, str, int]):
        self._storage.add_quarantine(*item)
