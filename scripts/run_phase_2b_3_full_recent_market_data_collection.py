from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from foundation.infrastructure.full_recent_market_data_collection import (
    build_completion_summary,
    load_records,
    pending_records,
    replace_checkpoint_record,
    validate_input,
)
from foundation.infrastructure.recent_market_data import collect_symbol


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-universe", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    policy = json.loads(Path("config/sources/full_recent_market_data_collection_policy.json").read_text(encoding="utf-8"))
    acquisition_policy = json.loads(Path("config/sources/recent_market_data_acquisition_policy.json").read_text(encoding="utf-8"))
    user_agent_name = acquisition_policy["required_user_agent_environment_variable"]
    user_agent = os.environ.get(user_agent_name, "").strip()
    if not user_agent:
        raise SystemExit(f"Set {user_agent_name} before collection.")

    input_records = load_records(Path(args.active_universe))
    validate_input(input_records, policy)

    output_dir = Path("data/staged/recent_market_data") / args.operating_date
    raw_dir = Path("data/raw/recent_market_data") / args.operating_date
    checkpoint_path = output_dir / "collection_checkpoint.json"
    summary_path = output_dir / "full_collection_summary.json"
    attestation_path = output_dir / "full_collection_attestation.json"

    checkpoint = {"records": []}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint_records = list(checkpoint.get("records") or [])

    work = pending_records(
        input_records,
        checkpoint_records,
        retry_failed=args.retry_failed,
        retryable_statuses=set(policy["retryable_statuses"]),
    )
    if args.limit is not None:
        work = work[: args.limit]

    delay = 1.0 / float(acquisition_policy["maximum_requests_per_second"])
    progress_interval = int(policy["progress_interval_records"])
    for position, record in enumerate(work, start=1):
        symbol = record["symbol"].upper()
        result = collect_symbol(
            security_id=record["security_id"],
            symbol=symbol,
            policy=acquisition_policy,
            user_agent=user_agent,
            raw_path=raw_dir / f"{symbol}.json",
        )
        checkpoint_records = replace_checkpoint_record(checkpoint_records, result.record)
        write_json(checkpoint_path, {"records": checkpoint_records})
        if position % progress_interval == 0 or position == len(work):
            progress = build_completion_summary(
                input_records, checkpoint_records, policy, args.operating_date
            )
            print(
                f"Progress: {progress['completed_unique_records']}/"
                f"{progress['input_records']} complete; "
                f"{progress['remaining_records']} remaining"
            )
            write_json(summary_path, progress)
        time.sleep(delay)

    summary = build_completion_summary(
        input_records, checkpoint_records, policy, args.operating_date
    )
    write_json(summary_path, summary)
    if summary["collection_complete"]:
        write_json(
            attestation_path,
            {
                **summary,
                "attestation_status": "COMPLETE",
                "full_history_collection_authorized": False,
                "analytics_authorized": False,
                "forecasting_authorized": False,
            },
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
