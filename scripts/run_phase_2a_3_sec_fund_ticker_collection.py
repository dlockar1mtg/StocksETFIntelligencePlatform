from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.infrastructure.sec_fund_tickers import (
    fetch_sec_payload,
    parse_fund_ticker_payload,
    reconcile_to_universe,
    write_immutable,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True, help="Path to governed Robinhood universe JSON")
    parser.add_argument("--operating-date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    document = json.loads(universe_path.read_text(encoding="utf-8"))
    universe = document.get("records", document if isinstance(document, list) else None)
    if not isinstance(universe, list):
        raise RuntimeError("Universe input must be a list or contain records")

    payload, lineage = fetch_sec_payload()
    raw_path = ROOT / "data" / "raw" / "sec" / args.operating_date / "company_tickers_mf.json"
    write_immutable(raw_path, payload)
    sec_rows = parse_fund_ticker_payload(payload)
    result = reconcile_to_universe(sec_rows, universe)
    result.update({
        "operating_date": args.operating_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_lineage": lineage,
        "raw_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
    })
    output = ROOT / "data" / "staged" / "structural_metadata" / args.operating_date / "sec_fund_ticker_reconciliation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("total_universe_records", "matched", "conflicted", "unmatched")}, indent=2))
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
