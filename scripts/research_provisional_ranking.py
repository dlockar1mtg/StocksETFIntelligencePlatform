"""Phase 4.2 research: walk-forward test of within-group ETF ranking against the pre-registered gate.

Usage: python scripts/research_provisional_ranking.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market import provisional_ranking as R  # noqa: E402
from foundation.market import provisional_timing as T  # noqa: E402

POLICY = ROOT / "config" / "market" / "provisional_ranking_policy.json"
DATA = ROOT / "data" / "curated" / "hosted_etf"


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    status = json.loads((DATA / "market_data_status.json").read_text(encoding="utf-8"))
    model = [f["symbol"] for f in status["funds"] if f["usage"] == "MODEL"]
    funds = R.load_features(DATA / "month_end_features.csv")
    last_year = max(int(m[:4]) for f in funds.values() for m in f["months"])
    groups = R.point_in_time_groups(funds, model, range(2003, last_year + 1))
    panel = R.build_panel(funds, model, groups)
    wf = R.walk_forward(panel, policy)
    verdict = R.gate(wf, policy)
    timing = T.timing_study(funds, model, groups, policy)
    report = {"policy_id": policy["policy_id"], "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "panel_rows": len(panel), "funds": len(model), "walk_forward": wf, "gate": verdict, "timing": timing,
              "known_limitations": policy["known_limitations"]}
    out = DATA / "research" / "provisional_ranking_research.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=lambda o: o.item()) + "\n", encoding="utf-8")
    for h in ("12m", "36m"):
        for key, r in wf[h]["results"].items():
            print(h, key, {k: r[k] for k in ("test_years", "top_quintile_mean_excess", "bottom_quintile_mean_excess",
                                              "share_years_top_beats_median", "share_years_top_beats_bottom")})
        print(h, "IC", {k: (v["mean_ic"], v["t_yearly"]) for k, v in wf[h]["factor_ic_full_sample"].items()})
    print("gate", verdict)
    for fam, rules in timing.items():
        print("timing", fam, {k: (v["share_beating"], v["median_edge"], v["passes_gate"]) for k, v in rules.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
