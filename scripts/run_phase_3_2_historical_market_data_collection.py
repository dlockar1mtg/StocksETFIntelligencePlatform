from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from foundation.infrastructure.historical_market_data import collect_symbol

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "sources" / "historical_market_data_collection_policy.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-universe", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--symbols", nargs="*")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    user_agent = os.environ.get("MARKET_DATA_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit("MARKET_DATA_USER_AGENT is required")

    document = json.loads(Path(args.candidate_universe).read_text(encoding="utf-8"))
    records = list(document.get("records") or [])
    if len(records) != int(policy["required_candidate_count"]):
        raise SystemExit(f"Expected {policy['required_candidate_count']} candidates but found {len(records)}")
    if any(r.get("screen_state") != policy["required_candidate_state"] for r in records):
        raise SystemExit("Candidate universe contains a noneligible record")

    requested = {s.upper() for s in (args.symbols or [])}
    if requested:
        records = [r for r in records if str(r.get("symbol", "")).upper() in requested]
        missing = requested - {str(r.get("symbol", "")).upper() for r in records}
        if missing:
            raise SystemExit(f"Requested symbols not found: {', '.join(sorted(missing))}")

    out_dir = ROOT / "data" / "staged" / "historical_market_data" / args.operating_date
    raw_dir = ROOT / "data" / "raw" / "historical_market_data" / args.operating_date
    checkpoint_path = out_dir / "historical_collection_checkpoint.json"
    summary_path = out_dir / "historical_collection_summary.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = {}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        existing = {r["security_id"]: r for r in checkpoint.get("records", [])}

    retryable = set(policy["retryable_statuses"])
    pending = []
    for record in records:
        prior = existing.get(record["security_id"])
        if prior is None or (args.retry_failed and prior.get("collection_status") in retryable):
            pending.append(record)

    for index, record in enumerate(pending, start=1):
        symbol = str(record["symbol"]).upper()
        try:
            result = collect_symbol(
                security_id=str(record["security_id"]),
                symbol=symbol,
                policy=policy,
                user_agent=user_agent,
                raw_path=raw_dir / f"{record['security_id']}.json",
            )
            existing[str(record["security_id"])] = result.record
        except ValueError as exc:
            existing[str(record["security_id"])] = {
                "security_id": str(record["security_id"]), "symbol": symbol,
                "provider_id": policy["provider_id"], "provider_symbol": symbol,
                "collection_status": "INVALID_SYMBOL", "collection_error": str(exc),
                "authority": {"return_calculation": False, "risk_analytics": False, "forecasting": False},
            }
        checkpoint_path.write_text(json.dumps({"phase": "3.2", "records": list(existing.values())}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if index % int(policy["progress_interval_records"]) == 0 or index == len(pending):
            print(f"Progress: {index}/{len(pending)} requested; {len(existing)} checkpoint records")
        if index < len(pending):
            time.sleep(float(policy["minimum_seconds_between_requests"]))

    selected_ids = {str(r["security_id"]) for r in records}
    selected_results = [existing[i] for i in selected_ids if i in existing]
    counts = {}
    for record in selected_results:
        status = record["collection_status"]
        counts[status] = counts.get(status, 0) + 1
    summary = {
        "phase": "3.2",
        "operating_date": args.operating_date,
        "requested_records": len(records),
        "completed_records": len(selected_results),
        "status_counts": dict(sorted(counts.items())),
        "required_seed_symbols": policy["required_seed_symbols"],
        "full_universe_collection_authorized": False,
        "return_calculation_authorized": False,
        "risk_analytics_authorized": False,
        "forecasting_authorized": False,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
