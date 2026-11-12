import argparse
from pathlib import Path

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.runners.portability.fn_api_runner import FnApiRunner

from fleet.config import load_config
from fleet.pipeline.transforms import (
    QUARANTINE,
    VALID,
    EnrichFn,
    Record,
    ValidateFn,
    WriteFn,
    WriteQuarantineFn,
    read_pubsub,
    read_records,
)


def run(source: Path, db: Path, config: Path) -> None:
    run_records(read_records(source), db, config)


def run_records(records: list[Record], db: Path, config: Path) -> None:
    cfg = load_config(config)
    db.parent.mkdir(parents=True, exist_ok=True)
    # In-process Python runner: DirectRunner would hand off to Prism, which downloads a binary.
    # One worker because SQLite is the V1 sink (BigQuery is V2).
    options = PipelineOptions(direct_num_workers=1)
    with beam.Pipeline(runner=FnApiRunner(), options=options) as p:
        checked = (
            p
            | "Read" >> beam.Create(records)
            | "Validate" >> beam.ParDo(ValidateFn(cfg)).with_outputs(QUARANTINE, main=VALID)
        )
        (
            checked[VALID]
            | "Enrich" >> beam.ParDo(EnrichFn(cfg))
            | "Write" >> beam.ParDo(WriteFn(str(db)))
        )
        checked[QUARANTINE] | "Quarantine" >> beam.ParDo(WriteQuarantineFn(str(db)))


def main() -> None:
    p = argparse.ArgumentParser(
        prog="fleet.pipeline", description="Validate, enrich, store messages"
    )
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="sample dir or capture .jsonl")
    source.add_argument("--subscription", help="projects/<p>/subscriptions/<s> to drain")
    p.add_argument("--db", type=Path, default=Path("out/pipeline.db"))
    p.add_argument("--config", type=Path, default=Path("config/fleet.yaml"))
    args = p.parse_args()
    records = read_records(args.input) if args.input else read_pubsub(args.subscription)
    run_records(records, args.db, args.config)


if __name__ == "__main__":
    main()
