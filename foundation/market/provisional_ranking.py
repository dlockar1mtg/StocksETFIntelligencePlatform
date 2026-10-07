"""Provisional ETF ranking (Phase 4.2): which funds in a peer group tend to do better next, tested
walk-forward on the model universe's month-end features. See config/market/provisional_ranking_policy.json.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from statistics import mean, median

import numpy as np

from foundation.market import provisional_peer_groups as G

FACTORS = ("mom_12_1", "mom_6", "trend_200", "stretch_60m", "vol_1y", "maxdd_3y", "dd_now", "yield_12m")
# log_adv_63 is computed but excluded: selecting today's liquid funds makes past illiquidity a survivorship artifact (policy amendment 2026-10-06).
FAMILY = (("US_EQUITY", ("US_EQUITY", "US_SECTOR")), ("INTL_EQUITY", ("INTL_",)), ("BONDS", ("BOND_",)))


def family_of(group: str) -> str:
    for fam, prefixes in FAMILY:
        if group.startswith(prefixes):
            return fam
    return "OTHER"


def _f(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def load_features(path) -> dict[str, dict]:
    rows: dict[str, list[dict]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as handle:
        for r in csv.DictReader(handle):
            rows[r["symbol"]].append(r)
    funds = {}
    for sym, rs in rows.items():
        rs.sort(key=lambda r: r["date"])
        tr = np.array([_f(r["tr_index"]) for r in rs])
        close = np.array([_f(r["close"]) for r in rs])
        months = [r["date"][:7] for r in rs]
        f = {"security_id": rs[0]["security_id"], "months": months, "index": {m: i for i, m in enumerate(months)},
             "date": [r["date"] for r in rs], "tr": tr, "close": close}
        for k in ("trend_200", "vol_1y", "dd_now", "maxdd_3y", "adv_63", "div_12m"):
            f[k] = np.array([_f(r[k]) for r in rs])
        funds[sym] = f
    return funds


def _back(f: dict, i: int, k: int) -> float:
    """tr k month-ends before index i, only when those month-ends are consecutive calendar months."""
    j = i - k
    if j < 0:
        return math.nan
    a, b = f["months"][j], f["months"][i]
    if (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7]) != k:
        return math.nan
    return f["tr"][j]


def factor_row(f: dict, i: int) -> dict[str, float]:
    tr = f["tr"]
    t1, t6, t12 = _back(f, i, 1), _back(f, i, 6), _back(f, i, 12)
    window = tr[max(0, i - 59):i + 1]
    return {
        "mom_12_1": t1 / t12 - 1 if t12 == t12 and t1 == t1 else math.nan,
        "mom_6": tr[i] / t6 - 1 if t6 == t6 else math.nan,
        "trend_200": f["trend_200"][i],
        "stretch_60m": tr[i] / window.mean() if len(window) >= 60 else math.nan,
        "vol_1y": f["vol_1y"][i],
        "maxdd_3y": f["maxdd_3y"][i],
        "dd_now": f["dd_now"][i],
        "yield_12m": f["div_12m"][i] / f["close"][i] if f["close"][i] > 0 else math.nan,
        "log_adv_63": math.log(f["adv_63"][i]) if f["adv_63"][i] > 0 else math.nan,
    }


def forward(f: dict, i: int, k: int) -> float:
    j = i + k
    if j >= len(f["months"]):
        return math.nan
    a, b = f["months"][i], f["months"][j]
    if (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7]) != k:
        return math.nan
    r = f["tr"][j] / f["tr"][i]
    return r - 1 if k <= 12 else r ** (12 / k) - 1


def point_in_time_groups(funds: dict, symbols: list[str], years: range) -> dict[int, dict[str, dict]]:
    """Classification at each December, from the trailing 36 months only."""
    returns = {s: G.monthly_returns(dict(zip(f["months"], f["tr"]))) for s, f in funds.items()}
    return {y: G.classify_all(returns, symbols, f"{y}-12") for y in years}


def build_panel(funds: dict, model_symbols: list[str], groups_by_year: dict[int, dict]) -> list[dict]:
    """One row per (month-end, fund) with factors, group and peer-relative forward returns."""
    rows = []
    for sym in model_symbols:
        f = funds.get(sym)
        if not f:
            continue
        for i, m in enumerate(f["months"]):
            y = int(m[:4]) if m[5:7] == "12" else int(m[:4]) - 1
            g = groups_by_year.get(y, {}).get(sym)
            if not g:
                continue
            rows.append({"month": m, "symbol": sym, "group": g["group"], **factor_row(f, i),
                         "fwd12": forward(f, i, 12), "fwd36": forward(f, i, 36)})
    by = defaultdict(list)
    for r in rows:
        by[(r["month"], r["group"])].append(r)
    for members in by.values():
        for target in ("fwd12", "fwd36"):
            vals = [r[target] for r in members if r[target] == r[target]]
            med = median(vals) if len(vals) >= 5 else math.nan
            for r in members:
                r[f"{target}_excess"] = r[target] - med if r[target] == r[target] and med == med else math.nan
    return rows


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 5:
        return math.nan
    rx, ry = np.array(_rank(x)), np.array(_rank(y))
    if rx.std() == 0 or ry.std() == 0:
        return math.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def monthly_ic(panel: list[dict], target: str) -> dict[str, dict[str, float]]:
    """{factor: {month: size-weighted mean within-group IC}} over rankable groups."""
    by = defaultdict(list)
    for r in panel:
        if r["group"] not in ("INSUFFICIENT_HISTORY", "SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "IDIOSYNCRATIC"):
            by[(r["month"], r["group"])].append(r)
    out: dict[str, dict[str, float]] = {k: {} for k in FACTORS}
    acc: dict = defaultdict(lambda: [0.0, 0])
    for (m, g), members in by.items():
        for k in FACTORS:
            pairs = [(r[k], r[target]) for r in members if r[k] == r[k] and r[target] == r[target]]
            ic = spearman([a for a, _ in pairs], [b for _, b in pairs])
            if ic == ic:
                acc[(k, m)][0] += ic * len(pairs)
                acc[(k, m)][1] += len(pairs)
    for (k, m), (s, n) in acc.items():
        out[k][m] = s / n
    return out


def yearly_t(ic_by_month: dict[str, float], months: set[str] | None = None) -> tuple[float, float, int]:
    """Mean IC, t-stat on yearly means (overlapping 12-month targets make months dependent)."""
    years = defaultdict(list)
    for m, v in ic_by_month.items():
        if months is None or m in months:
            years[m[:4]].append(v)
    ym = [mean(v) for v in years.values() if v]
    if len(ym) < 2:
        return (ym[0] if ym else math.nan), math.nan, len(ym)
    sd = float(np.std(ym, ddof=1))
    return float(mean(ym)), (float(mean(ym)) / (sd / math.sqrt(len(ym))) if sd else math.nan), len(ym)


def select_factors(ic: dict[str, dict[str, float]], before_month: str, horizon: int, policy: dict) -> dict[str, int]:
    """Factors (with sign) whose IC was reliably non-zero on targets fully realized before `before_month`."""
    y, m = int(before_month[:4]), int(before_month[5:7])
    cutoff_index = y * 12 + m - 1 - horizon

    def realized(month: str) -> bool:
        return int(month[:4]) * 12 + int(month[5:7]) - 1 <= cutoff_index

    chosen = {}
    for k in FACTORS:
        train = {mm: v for mm, v in ic[k].items() if realized(mm)}
        mu, t, years = yearly_t(train)
        if years >= 5 and t == t and abs(t) >= 2.0:
            chosen[k] = 1 if mu > 0 else -1
    return chosen


def composite(members: list[dict], chosen: dict[str, int]) -> list[float]:
    """Mean of signed within-group percentile ranks; missing factors are skipped, never imputed."""
    scores = [[] for _ in members]
    for k, sign in chosen.items():
        idx = [i for i, r in enumerate(members) if r[k] == r[k]]
        if len(idx) < 2:
            continue
        ranks = _rank([members[i][k] * sign for i in idx])
        top = max(ranks) or 1.0
        for i, rk in zip(idx, ranks):
            scores[i].append(rk / top)
    return [mean(s) if s else math.nan for s in scores]


def walk_forward(panel: list[dict], policy: dict) -> dict:
    out = {}
    for horizon, target in ((12, "fwd12_excess"), (36, "fwd36_excess")):
        ic = monthly_ic(panel, target)
        by = defaultdict(list)
        for r in panel:
            by[(r["month"], r["group"])].append(r)
        first = int(policy["walk_forward"]["first_test_year"])
        yearly = defaultdict(lambda: defaultdict(list))
        selections = {}
        for (m, g), members in sorted(by.items()):
            if int(m[:4]) < first or g in policy["taxonomy"]["no_call_groups"]:
                continue
            year_start = f"{m[:4]}-01"
            if year_start not in selections:
                selections[year_start] = select_factors(ic, year_start, horizon, policy)
            chosen = selections[year_start]
            live = [r for r in members if r[target] == r[target]]
            if not chosen or len(live) < int(policy["taxonomy"]["minimum_peer_group_size"]):
                continue
            sc = composite(live, chosen)
            pairs = sorted((s, r[target]) for s, r in zip(sc, live) if s == s)
            if len(pairs) < 5:
                continue
            q = max(1, len(pairs) // 5)
            top, bottom = [v for _, v in pairs[-q:]], [v for _, v in pairs[:q]]
            fam = family_of(g)
            for key in ("ALL", fam):
                yearly[key][m[:4]].append((mean(top), mean(bottom)))
        res = {}
        for key, years in yearly.items():
            ys = sorted(years)
            tops = [mean(t for t, _ in years[y]) for y in ys]
            bots = [mean(b for _, b in years[y]) for y in ys]
            res[key] = {"test_years": len(ys), "first_year": ys[0] if ys else None, "last_year": ys[-1] if ys else None,
                        "top_quintile_mean_excess": round(mean(tops), 4) if tops else None,
                        "bottom_quintile_mean_excess": round(mean(bots), 4) if bots else None,
                        "share_years_top_beats_median": round(sum(t > 0 for t in tops) / len(tops), 3) if tops else None,
                        "share_years_top_beats_bottom": round(sum(t > b for t, b in zip(tops, bots)) / len(tops), 3) if tops else None,
                        "by_year": {y: {"top": round(t, 4), "bottom": round(b, 4)} for y, t, b in zip(ys, tops, bots)}}
        ic_summary = {}
        for k in FACTORS:
            mu, t, n = yearly_t(ic[k])
            ic_summary[k] = {"mean_ic": None if mu != mu else round(mu, 4), "t_yearly": None if t != t else round(t, 2), "years": n}
        out[f"{horizon}m"] = {"results": res, "factor_ic_full_sample": ic_summary,
                              "selections_by_test_year": {k[:4]: v for k, v in selections.items()}}
    return out


def gate(wf: dict, policy: dict) -> dict:
    g12, g36 = policy["gate"]["horizon_12m"], policy["gate"]["horizon_36m"]
    a12, a36 = wf["12m"]["results"].get("ALL"), wf["36m"]["results"].get("ALL")

    def ok12(r):
        return bool(r) and r["test_years"] >= g12["min_test_years"] and r["top_quintile_mean_excess"] >= g12["min_top_quintile_mean_excess"] \
            and r["share_years_top_beats_median"] >= g12["min_share_of_years_top_beats_median"] \
            and r["share_years_top_beats_bottom"] >= g12["min_share_of_years_top_beats_bottom"]
    pass12 = ok12(a12)
    pass36 = bool(a36) and a36["test_years"] >= g36["min_test_years"] and a36["top_quintile_mean_excess"] >= g36["min_top_quintile_mean_excess_annualized"] \
        and a36["share_years_top_beats_median"] >= g36["min_share_of_years_top_beats_median"]
    families = {}
    for fam in ("US_EQUITY", "INTL_EQUITY", "BONDS", "OTHER"):
        r = wf["12m"]["results"].get(fam)
        families[fam] = bool(pass12 and r and r["test_years"] >= 3 and r["share_years_top_beats_median"] >= 0.55)
    return {"pass_12m": pass12, "pass_36m": pass36, "families_enabled": families}


def assign_call(pct: float, previous: str | None, bands: dict) -> str:
    if previous == "BUY" and pct >= 70:
        return "BUY"
    if previous == "AVOID" and pct <= 30:
        return "AVOID"
    if pct >= bands["BUY"]:
        return "BUY"
    if pct >= bands["ACCUMULATE"]:
        return "ACCUMULATE"
    if pct >= bands["HOLD"]:
        return "HOLD"
    return "AVOID"
