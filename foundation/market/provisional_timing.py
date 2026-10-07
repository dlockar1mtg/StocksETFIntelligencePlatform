"""When-to-buy evidence per group family (Phase 4.2): do simple timing rules for new money beat
plain monthly buying of the family's equal-weight index over 36 months, out of sample?"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median

from foundation.market import provisional_ranking as R

GRIDS = {"TREND_PAUSE": [0.0, 0.02, 0.05], "STRETCH_PAUSE": [1.3, 1.4, 1.5, 1.6],
         "WAIT_FOR_DIP": [0.10, 0.15, 0.20], "MOMENTUM_PAUSE": [0.0, -0.05]}
HORIZON, MAX_WAIT, FIRST_TEST = 36, 12, "2013-01"


def family_indexes(funds: dict, model: list[str], groups_by_year: dict) -> dict[str, list[tuple[str, float]]]:
    rets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for sym in model:
        f = funds.get(sym)
        if not f:
            continue
        for i in range(1, len(f["months"])):
            m = f["months"][i]
            y = int(m[:4]) - 1                      # groups set at the previous December
            g = groups_by_year.get(y, {}).get(sym, {}).get("group")
            if not g or g in ("INSUFFICIENT_HISTORY", "SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "IDIOSYNCRATIC"):
                continue
            if R._back(f, i, 1) == R._back(f, i, 1):
                rets[R.family_of(g)][m].append(f["tr"][i] / f["tr"][i - 1] - 1)
    out = {}
    for fam, by_month in rets.items():
        level, series = 100.0, []
        for m in sorted(by_month):
            if len(by_month[m]) >= 5:
                level *= 1 + mean(by_month[m])
                series.append((m, level))
        out[fam] = series
    return out


def _signals(series: list[tuple[str, float]], k: int) -> dict:
    vals = [v for _, v in series[:k + 1]]
    cur = vals[-1]
    return {"trend": cur / mean(vals[-10:]) if len(vals) >= 10 else None,
            "stretch": cur / mean(vals[-60:]) if len(vals) >= 60 else None,
            "dd": cur / max(vals) - 1, "mom": cur / vals[-13] - 1 if len(vals) >= 13 else None}


def _pause(rule: str, p: float, s: dict) -> bool:
    if rule == "TREND_PAUSE":
        return s["trend"] is not None and s["trend"] < 1 - p
    if rule == "STRETCH_PAUSE":
        return s["stretch"] is not None and s["stretch"] > p
    if rule == "WAIT_FOR_DIP":
        return s["dd"] > -p
    return s["mom"] is not None and s["mom"] < p


def simulate(series, cash: dict[str, float], start: int, rule: str | None, p: float | None) -> float | None:
    if start + HORIZON >= len(series):
        return None
    units = held = 0.0
    waited = 0
    for k in range(start, start + HORIZON):
        m = series[k][0]
        if k > start:
            held *= 1 + cash.get(m, 0.0)
        held += 100
        if rule and _pause(rule, p, _signals(series, k)) and waited < MAX_WAIT:
            waited += 1
            continue
        units += held / series[k][1]
        held, waited = 0.0, 0
    end = series[start + HORIZON]
    held *= 1 + cash.get(end[0], 0.0)
    return units * end[1] + held


def timing_study(funds: dict, model: list[str], groups_by_year: dict, policy: dict) -> dict:
    bil = funds.get("BIL")
    cash = {}
    if bil:
        for i in range(1, len(bil["months"])):
            cash[bil["months"][i]] = bil["tr"][i] / bil["tr"][i - 1] - 1
    first_cash = min(cash) if cash else "9999-99"
    out = {}
    for fam, series in family_indexes(funds, model, groups_by_year).items():
        starts = [k for k, (m, _) in enumerate(series) if m >= first_cash and k + HORIZON < len(series)]
        edges = {}
        for k in starts:
            base = simulate(series, cash, k, None, None)
            for rule, grid in GRIDS.items():
                for p in grid:
                    edges[(rule, p, k)] = simulate(series, cash, k, rule, p) / base - 1
        fam_out = {}
        for rule, grid in GRIDS.items():
            oos = []
            for k in starts:
                if series[k][0] < FIRST_TEST:
                    continue
                done = [j for j in starts if j + HORIZON <= k]
                if len(done) < 12:
                    continue
                best = max(grid, key=lambda p: mean(edges[(rule, p, j)] for j in done))
                oos.append(edges[(rule, best, k)])
            passes = bool(oos) and sum(e > 0 for e in oos) / len(oos) >= 0.6 and median(oos) >= 0.005
            done_all = [j for j in starts]
            chosen_now = max(grid, key=lambda p: mean(edges[(rule, p, j)] for j in done_all)) if done_all else None
            fam_out[rule] = {"parameter_now": chosen_now, "starts": len(oos), "share_beating": round(sum(e > 0 for e in oos) / len(oos), 3) if oos else None,
                             "median_edge": round(median(oos), 4) if oos else None, "worst_edge": round(min(oos), 4) if oos else None,
                             "passes_gate": passes}
        now = _signals(series, len(series) - 1) if series else {}
        out[fam] = {**fam_out, "_now": {"month": series[-1][0] if series else None,
                                        **{k: (None if v is None else round(v, 4)) for k, v in now.items()}}}
    return out


def reading(family_result: dict) -> dict:
    """When-to-buy reading for a family: a passing rule's current verdict, else steady buying."""
    now = family_result.get("_now") or {}
    for rule in ("WAIT_FOR_DIP", "STRETCH_PAUSE", "TREND_PAUSE", "MOMENTUM_PAUSE"):
        r = family_result.get(rule) or {}
        if not r.get("passes_gate"):
            continue
        p = r["parameter_now"]
        signal = {"trend": now.get("trend"), "stretch": now.get("stretch"), "dd": now.get("dd"), "mom": now.get("mom")}
        if any(v is None for v in signal.values()):
            continue
        wait = _pause(rule, p, signal)
        return {"rule": rule, "parameter": p, "verdict": "WAIT" if wait else "BUY_NOW", "as_of_month": now.get("month"),
                "drawdown": now.get("dd"), "stretch": now.get("stretch"),
                "evidence": {"share_beating": r["share_beating"], "median_edge": r["median_edge"], "starts": r["starts"]}}
    return {"rule": None, "verdict": "STEADY_BUYING", "as_of_month": now.get("month"),
            "evidence": "No timing rule beat plain monthly buying for this family out of sample."}
