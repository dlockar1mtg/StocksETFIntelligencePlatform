"""Phase 4.3 cost test: does a lower official expense ratio predict better peer-relative returns?
The sign is fixed in advance (lower is better); nothing is fitted. See provisional_ranking_policy.json cost_test."""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

import numpy as np

from foundation.market import provisional_ranking as R
from foundation.market import sec_expense_ratios as X


def attach_cost(panel: list[dict], history: dict) -> None:
    for r in panel:
        v = X.ratio_on(history, r["symbol"], f"{r['month']}-28")
        r["neg_cost"] = -v if v is not None else math.nan


def cost_test(panel: list[dict], policy: dict) -> dict:
    spec = policy["cost_test"]
    first = int(spec["test_years_from"])
    out = {}
    for horizon, target in (("12m", "fwd12_excess"), ("36m", "fwd36_excess")):
        by = defaultdict(list)
        for r in panel:
            if int(r["month"][:4]) >= first and r["group"] not in policy["taxonomy"]["no_call_groups"]:
                by[(r["month"], r["group"])].append(r)
        ic_year, top_year, bot_year = defaultdict(list), defaultdict(list), defaultdict(list)
        for (m, g), members in by.items():
            live = [r for r in members if r["neg_cost"] == r["neg_cost"] and r[target] == r[target]]
            if len(live) < 5 or len({r["neg_cost"] for r in live}) < 3:
                continue
            ic = R.spearman([r["neg_cost"] for r in live], [r[target] for r in live])
            if ic == ic:
                ic_year[m[:4]].append(ic)
            live.sort(key=lambda r: r["neg_cost"])
            q = max(1, len(live) // 5)
            top_year[m[:4]].append(mean(r[target] for r in live[-q:]))       # cheapest fifth
            bot_year[m[:4]].append(mean(r[target] for r in live[:q]))        # most expensive fifth
        years = sorted(ic_year)
        ym = [mean(ic_year[y]) for y in years]
        tops = [mean(top_year[y]) for y in years]
        bots = [mean(bot_year[y]) for y in years]
        sd = float(np.std(ym, ddof=1)) if len(ym) > 1 else math.nan
        t = mean(ym) / (sd / math.sqrt(len(ym))) if ym and sd and sd == sd else math.nan
        out[horizon] = {"test_years": len(years), "mean_ic": round(mean(ym), 4) if ym else None, "t_yearly": None if t != t else round(t, 2),
                        "cheapest_quintile_mean_excess": round(mean(tops), 4) if tops else None,
                        "most_expensive_quintile_mean_excess": round(mean(bots), 4) if bots else None,
                        "share_years_cheapest_beats_median": round(sum(x > 0 for x in tops) / len(tops), 3) if tops else None,
                        "share_years_cheapest_beats_most_expensive": round(sum(a > b for a, b in zip(tops, bots)) / len(tops), 3) if tops else None,
                        "by_year": {y: {"ic": round(i, 3), "cheapest": round(a, 4), "most_expensive": round(b, 4)} for y, i, a, b in zip(years, ym, tops, bots)}}
    g = spec["gate"]
    r12 = out["12m"]
    out["passes_gate"] = bool(r12["test_years"] >= g["min_test_years"] and (r12["mean_ic"] or 0) > g["min_mean_ic_12m"]
                              and (r12["t_yearly"] or 0) >= g["min_t_yearly_12m"]
                              and (r12["cheapest_quintile_mean_excess"] or 0) >= g["min_cheapest_quintile_mean_excess_12m"]
                              and (r12["share_years_cheapest_beats_median"] or 0) >= g["min_share_years_cheapest_beats_median"])
    return out


def calls_enabled(result: dict, policy: dict) -> bool:
    """Cost calls run on the 36-month evidence (owner amendment of 2026-10-07)."""
    spec = policy["cost_test"]
    if spec.get("calls_horizon") != "36m":
        return bool(result.get("passes_gate"))
    g, r = spec["calls_gate_36m"], result["36m"]
    return bool(r["test_years"] >= g["min_test_years"] and (r["t_yearly"] or 0) >= g["min_t_yearly"]
                and (r["share_years_cheapest_beats_most_expensive"] or 0) >= g["min_share_years_cheapest_beats_most_expensive"])
