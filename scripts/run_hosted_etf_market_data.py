"""Phase 4.1 hosted run: update daily series for the model universe and write month-end features.

Usage: python scripts/run_hosted_etf_market_data.py [--full] [--only VOO SCHD] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.infrastructure.yahoo_chart_daily import ChartClient  # noqa: E402
from foundation.market import hosted_market_data as H  # noqa: E402

POLICY = ROOT / "config" / "market" / "hosted_market_data_policy.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="refetch full history for every fund")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    storage = policy["storage"]
    cache = ROOT / storage["daily_cache_dir"]
    funds = H.load_universe(ROOT, policy)
    if args.only:
        funds = [f for f in funds if f["symbol"] in {s.upper() for s in args.only}]
    if args.limit:
        funds = funds[:args.limit]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    full = args.full or now.weekday() == int(policy["incremental"]["full_refresh_weekday"])
    client = ChartClient(policy["provider"])
    fetch = lambda symbol, start: client.fetch(symbol, start=start, now=now)  # noqa: E731
    records, started = [], time.monotonic()
    for k, fund in enumerate(funds, 1):
        records.append(H.update_fund(fund, fetch, policy, now, cache, full_refresh=full))
        if k % 100 == 0 or k == len(funds):
            bad = sum(1 for r in records if r["failures"])
            print(f"{k}/{len(funds)} funds, {bad} with issues, {time.monotonic() - started:.0f}s", flush=True)
    rows = []
    for fund in funds:
        rows.extend(H.month_end_features(fund, H.read_cached_bars(cache, fund["symbol"])))
    features = ROOT / storage["month_end_features_path"]
    features.parent.mkdir(parents=True, exist_ok=True)
    features.write_text(H.features_csv(rows), encoding="utf-8")
    summary = {state: sum(1 for r in records if r["quality_status"] == state) for state in ("PASS", "PROVISIONAL", "QUARANTINED", "BLOCKED")}
    fresh = {state: sum(1 for r in records if r["freshness_state"] == state) for state in ("CURRENT", "AGING", "STALE", "UNKNOWN")}
    status = {"policy_id": policy["policy_id"], "generated_at_utc": now.isoformat(), "mode": "FULL" if full else "INCREMENTAL",
              "fund_count": len(records), "quality_summary": summary, "freshness_summary": fresh,
              "feature_rows": len(rows), "funds": records,
              "authority": policy["authority"]}
    out = ROOT / storage["status_path"]
    out.write_text(json.dumps(status, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"quality": summary, "freshness": fresh, "feature_rows": len(rows)}))
    seeds = [r for r in records if r["symbol"] in policy["universe"]["required_seed_symbols"]]
    if seeds and all(r["quality_status"] == "BLOCKED" for r in seeds):
        print("Every seed fund is blocked: failing the run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
