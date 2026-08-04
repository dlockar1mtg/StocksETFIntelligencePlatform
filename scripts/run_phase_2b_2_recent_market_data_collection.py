from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

from foundation.infrastructure.recent_market_data import collect_symbol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-universe", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--symbols", nargs="*")
    args = parser.parse_args()

    policy = json.loads(Path("config/sources/recent_market_data_acquisition_policy.json").read_text(encoding="utf-8"))
    user_agent = os.environ.get(policy["required_user_agent_environment_variable"], "").strip()
    if not user_agent:
        raise SystemExit(f"Set {policy['required_user_agent_environment_variable']} before collection.")

    document = json.loads(Path(args.active_universe).read_text(encoding="utf-8"))
    records = list(document.get("records") or [])
    requested = {value.upper() for value in (args.symbols or [])}
    if requested:
        records = [record for record in records if str(record.get("symbol", "")).upper() in requested]
    if args.limit is not None:
        records = records[: args.limit]

    output_dir = Path("data/staged/recent_market_data") / args.operating_date
    raw_dir = Path("data/raw/recent_market_data") / args.operating_date
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "collection_checkpoint.json"
    checkpoint = {"records": []}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    completed = {record["security_id"] for record in checkpoint.get("records", [])}

    delay = 1.0 / float(policy["maximum_requests_per_second"])
    for record in records:
        security_id = record["security_id"]
        symbol = record["symbol"].upper()
        if security_id in completed:
            continue
        result = collect_symbol(
            security_id=security_id,
            symbol=symbol,
            policy=policy,
            user_agent=user_agent,
            raw_path=raw_dir / f"{symbol}.json",
        )
        checkpoint["records"].append(result.record)
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        time.sleep(delay)

    statuses = Counter(record["collection_status"] for record in checkpoint["records"])
    summary = {
        "phase": "2B.2",
        "operating_date": args.operating_date,
        "provider_id": policy["provider_id"],
        "requested_records": len(records),
        "completed_records": len(checkpoint["records"]),
        "status_counts": dict(sorted(statuses.items())),
        "required_seed_symbols": policy["required_seed_symbols"],
        "selection_principle": policy["selection_principle"],
        "target_universe_size": policy["target_universe_size"],
        "full_history_collection_authorized": policy["authority"]["full_history_collection"],
        "forecasting_authorized": policy["authority"]["forecasting"],
    }
    (output_dir / "recent_market_data_collection_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
