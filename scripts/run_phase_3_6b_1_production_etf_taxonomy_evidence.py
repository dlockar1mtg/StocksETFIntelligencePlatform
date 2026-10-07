from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from foundation.market.production_etf_taxonomy_evidence import fetch_payload, normalize_payload, provider_error_record

ROOT = Path(__file__).resolve().parents[1]


def load_records(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = document.get("records") if isinstance(document, dict) else document
    if not isinstance(records, list):
        raise ValueError("INPUT_RECORD_ARRAY_MISSING")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.05)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()

    policy = json.loads((ROOT / "config/market/production_etf_taxonomy_evidence_policy.json").read_text(encoding="utf-8"))
    records = load_records(args.universe)
    required = int(policy["required_record_count"])
    if len(records) != required:
        raise ValueError(f"REQUIRED_RECORD_COUNT_MISMATCH:{len(records)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if args.output.exists():
        prior = json.loads(args.output.read_text(encoding="utf-8"))
        existing = {item["security_id"]: item for item in prior.get("records", [])}

    selected = records[: args.limit] if args.limit > 0 else records
    for index, item in enumerate(selected, start=1):
        security_id = item.get("security_id")
        symbol = item.get("symbol")
        if not security_id or not symbol:
            raise ValueError("MISSING_STABLE_IDENTITY")
        previous = existing.get(security_id)
        if previous and (previous.get("collection_state") != "PROVIDER_ERROR" or not args.retry_errors):
            continue
        try:
            payload = fetch_payload(symbol, policy)
            existing[security_id] = normalize_payload(security_id, symbol, payload)
        except Exception as exc:
            existing[security_id] = provider_error_record(security_id, symbol, exc)
        if index % 100 == 0:
            print(f"Processed {index}/{len(selected)}")
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    ordered = [existing[key] for key in sorted(existing)]
    state_counts = Counter(item["collection_state"] for item in ordered)
    output = {
        "phase": "3.6b.1",
        "required_record_count": required,
        "record_count": len(ordered),
        "collection_complete": len(ordered) == required,
        "collection_state_counts": dict(sorted(state_counts.items())),
        "records": ordered,
        "authority": policy["authority"],
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {key: value for key, value in output.items() if key != "records"}
    summary["taxonomy_snapshot_authorized"] = False
    summary["next_required_step"] = "AUTHORITATIVE_TAXONOMY_NORMALIZATION_AND_CERTIFICATION"
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
