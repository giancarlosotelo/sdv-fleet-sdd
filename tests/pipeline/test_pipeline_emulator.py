import os
import uuid
from pathlib import Path

import pytest

from fleet.cloud.storage import SqliteStorage
from fleet.pipeline.__main__ import run_records
from fleet.pipeline.transforms import read_pubsub
from tests.harness.real import require_service

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "contracts" / "samples"


@pytest.mark.real
def test_req100_pipeline_reads_from_pubsub_emulator(tmp_path):
    require_service("pubsub emulator", 8085)
    os.environ.setdefault("PUBSUB_EMULATOR_HOST", "127.0.0.1:8085")
    from google.cloud import pubsub_v1

    publisher, subscriber = pubsub_v1.PublisherClient(), pubsub_v1.SubscriberClient()
    run_id = uuid.uuid4().hex[:8]
    topic = publisher.topic_path("fleet-local", f"pipeline-{run_id}")
    subscription = subscriber.subscription_path("fleet-local", f"pipeline-{run_id}")
    publisher.create_topic(name=topic)
    subscriber.create_subscription(name=subscription, topic=topic)
    files = sorted((SAMPLES / "valid").glob("*.json")) + [
        SAMPLES / "malformed" / "not_json__json.json"
    ]
    for path in files:
        publisher.publish(topic, path.read_bytes()).result()

    records = read_pubsub(subscription)
    run_records(records, tmp_path / "p.db", ROOT / "config" / "fleet.yaml")

    storage = SqliteStorage(tmp_path / "p.db")
    assert len(records) == len(files)
    assert len(storage.telemetry()) == 2
    assert [a.hazard_type for a in storage.alerts(include_resolved=True)] == ["harsh_braking"]
    assert len(storage.quarantine()) == 1
