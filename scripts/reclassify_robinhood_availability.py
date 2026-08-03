from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from foundation.universe.robinhood_collector import classify_instrument


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-root", default="data")
    args = parser.parse_args()

    root = Path(args.output_root)
    staged = root / "staged" / args.operating_date
    raw_root = root / "raw" / args.operating_date / "robinhood"
    result_path = staged / "robinhood_availability_records.jsonl"

    candidates = {item["symbol"]: item for item in json.loads(Path(args.input_file).read_text(encoding="utf-8"))}
    existing = {}
    for line in result_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            existing[record["symbol"]] = record

    rebuilt = []
    for symbol, candidate in candidates.items():
        previous = existing[symbol]
        raw_path = raw_root / f"{symbol}.json"
        if previous.get("collection_error") or not raw_path.exists():
            rebuilt.append(previous)
            continue
        raw = raw_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        rebuilt.append(
            classify_instrument(
                candidate,
                payload,
                retrieved_at_utc=previous["verified_at_utc"],
                source_url=previous.get("source_url") or "LOCAL-RAW-RECLASSIFICATION",
                raw_sha256=hashlib.sha256(raw).hexdigest(),
            )
        )

    result_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in rebuilt), encoding="utf-8")
    print(json.dumps({"operating_date": args.operating_date, "reclassified_count": len(rebuilt), "result_path": str(result_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
