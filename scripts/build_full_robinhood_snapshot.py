from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.universe.full_snapshot import build_full_snapshot, write_full_snapshot


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--data-root", default="data")
    args = parser.parse_args()

    root = Path(args.data_root)
    staged = root / "staged" / args.operating_date
    candidates = json.loads((staged / "us_etf_discovery_candidates.json").read_text(encoding="utf-8"))
    broker_records = _load_jsonl(staged / "robinhood_availability_records.jsonl")
    exchange_manifest = json.loads((staged / "collection_manifest.json").read_text(encoding="utf-8"))
    broker_manifest = json.loads((staged / "robinhood_availability_manifest.json").read_text(encoding="utf-8"))

    snapshot = build_full_snapshot(
        candidates=candidates,
        broker_records=broker_records,
        operating_date=args.operating_date,
        exchange_manifest=exchange_manifest,
        broker_manifest=broker_manifest,
    )
    result = write_full_snapshot(
        snapshot,
        root / "certified" / args.operating_date / "robinhood_full_universe_snapshot.json",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
