"""Phase 4.5 research: walk-forward calibration test of the 3-year projections.

Usage: python scripts/research_provisional_projection.py
Writes data/curated/hosted_etf/research/provisional_projection_research.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market import provisional_projection as P  # noqa: E402
from foundation.market import provisional_ranking as R  # noqa: E402
from foundation.market import sec_expense_ratios as X  # noqa: E402

POLICY = ROOT / "config" / "market" / "provisional_projection_policy.json"
DATA = ROOT / "data" / "curated" / "hosted_etf"


def main() -> int:
    started = time.monotonic()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    status = json.loads((DATA / "market_data_status.json").read_text(encoding="utf-8"))
    model = [f["symbol"] for f in status["funds"] if f["usage"] == "MODEL"]
    funds = R.load_features(DATA / "month_end_features.csv")
    last_year = max(int(m[:4]) for f in funds.values() for m in f["months"])
    groups = R.point_in_time_groups(funds, model, range(2004, last_year))
    history_path = DATA / "expense_ratio_history.csv"
    history = X.load_history(history_path) if history_path.exists() else {}
    fee = (lambda s, d: X.ratio_on(history, s, d)) if history else None
    result = P.calibration_test(funds, model, groups, policy, fee)
    result["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result["known_limitations"] = policy["known_limitations"]
    out = DATA / "research" / "provisional_projection_research.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("observations", "overall", "families", "rules_now", "passes")}, indent=1))
    print("by start year", {y: (c.get("n"), c.get("inside_10_90")) for y, c in result["by_start_year"].items()})
    print(f"{time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
