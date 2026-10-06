"""Phase 4.4: the provisional ETF universe package for the UIP.

One record per model-universe fund (plus held funds outside it), carrying data state, provisional
peer group, readings, the within-group context, near-duplicate clusters with the better
implementation named, the family's when-to-buy reading, and the ranking call, which stays
NO_VALIDATED_RANKING_EDGE unless the pre-registered ranking gate passes.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import median

import numpy as np

from foundation.market import provisional_peer_groups as G
from foundation.market import provisional_ranking as R
from foundation.market import provisional_timing as T

NO_CALL_GROUPS = ("INSUFFICIENT_HISTORY", "SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "IDIOSYNCRATIC")
CLUSTER_CORRELATION, CLUSTER_MONTHS = 0.995, 36


def _r(x, places=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), places)


def readings_from_daily(bars) -> dict:
    """Readings at the latest close from the daily series (no future data exists by construction)."""
    if not bars or len(bars) < 22:
        return {}
    tr = np.array([b.tr_index for b in bars])
    close = np.array([b.close for b in bars])
    div = np.array([b.dividend for b in bars])

    def ret(n):
        return tr[-1] / tr[-1 - n] - 1 if len(tr) > n else None

    def ann(n):
        r = ret(n)
        return None if r is None else (1 + r) ** (252 / n) - 1
    logr = np.diff(np.log(tr[-253:]))
    window = tr[-757:]
    return {"as_of_date": bars[-1].day, "close": round(float(close[-1]), 4),
            "return_1m": _r(ret(21)), "return_3m": _r(ret(63)), "return_1y": _r(ret(252)),
            "annualized_3y": _r(ann(756)), "annualized_5y": _r(ann(1260)),
            "volatility_1y": _r(float(logr.std() * math.sqrt(252))) if len(logr) > 60 else None,
            "drawdown_now": _r(tr[-1] / tr.max() - 1), "max_drawdown_3y": _r(float((window / np.maximum.accumulate(window)).min() - 1)),
            "trend_200": _r(close[-1] / close[-200:].mean()) if len(close) >= 200 else None,
            "yield_12m": _r(div[-252:].sum() / close[-1]) if len(close) >= 252 else None,
            "history_from": bars[0].day}


def readings_from_monthly(f: dict | None) -> dict:
    """Fallback readings at the latest month-end when no daily series is available."""
    if not f or len(f["months"]) < 2:
        return {}
    i = len(f["months"]) - 1

    def back(k):
        v = R._back(f, i, k)
        return None if v != v else f["tr"][i] / v - 1
    r1, r12, r36, r60 = back(1), back(12), back(36), back(60)
    return {"as_of_date": f["date"][i], "close": float(f["close"][i]), "return_1m": _r(r1), "return_1y": _r(r12),
            "annualized_3y": _r(None if r36 is None else (1 + r36) ** (1 / 3) - 1),
            "annualized_5y": _r(None if r60 is None else (1 + r60) ** (1 / 5) - 1),
            "volatility_1y": _r(f["vol_1y"][i]), "drawdown_now": _r(f["dd_now"][i]), "max_drawdown_3y": _r(f["maxdd_3y"][i]),
            "trend_200": _r(f["trend_200"][i]), "yield_12m": _r(f["div_12m"][i] / f["close"][i] if f["close"][i] else None),
            "history_from": f["date"][0], "readings_basis": "MONTH_END"}


def _daily_returns(bars, sessions: int = 756) -> dict[str, float]:
    tail = bars[-(sessions + 1):]
    return {b.day: b.tr_index / a.tr_index - 1 for a, b in zip(tail, tail[1:])}


def clusters(symbols: list[str], returns: dict[str, dict[str, float]], end_month: str, cached_bars=None) -> list[list[str]]:
    """Funds that are effectively the same exposure: every pair in a cluster moves together at
    >= 0.998 correlation of daily returns over 3 years (complete linkage, so no chaining), with a
    volatility ratio within 5%. Without daily data, 36 monthly returns at >= 0.999 stand in."""
    series = {}
    for s in symbols:
        bars = cached_bars(s) if cached_bars else []
        if len(bars) > 757:
            series[s] = _daily_returns(bars)
    threshold = 0.998
    if len(series) < len(symbols) / 2:
        threshold, series = 0.999, {}
        for s in symbols:
            ms = sorted(m for m in returns.get(s, {}) if m <= end_month)[-CLUSTER_MONTHS:]
            if len(ms) == CLUSTER_MONTHS:
                series[s] = {m: returns[s][m] for m in ms}
    keys = sorted(series)
    corr = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            common = sorted(set(series[a]) & set(series[b]))
            if len(common) < 0.9 * min(len(series[a]), len(series[b])) or len(common) < 30:
                continue
            x = np.array([series[a][d] for d in common])
            y = np.array([series[b][d] for d in common])
            if x.std() and y.std() and 0.95 <= y.std() / x.std() <= 1.05:
                c = float(np.corrcoef(x, y)[0, 1])
                if c >= threshold:
                    corr[(a, b)] = c
    member = {s: {s} for s in keys}
    for (a, b), _ in sorted(corr.items(), key=lambda kv: -kv[1]):
        ca, cb = member[a], member[b]
        if ca is cb:
            continue
        if all(((x, y) if x < y else (y, x)) in corr for x in ca for y in cb):
            merged = ca | cb
            for s in merged:
                member[s] = merged
    out, seen = [], set()
    for s in keys:
        c = member[s]
        if len(c) > 1 and id(c) not in seen:
            seen.add(id(c))
            out.append(sorted(c))
    return out


def pick_best(members: list[dict]) -> dict:
    """Best implementation of one exposure: highest 3-year return net of costs, lowest expense ratio
    when every member has an official one and the returns are within 0.25% a year of the top."""
    scored = [m for m in members if m.get("annualized_3y") is not None]
    if not scored:
        return {}
    top = max(scored, key=lambda m: (m["annualized_3y"], m.get("liquidity") or 0))
    if all(m.get("expense_ratio") is not None for m in scored):
        close = [m for m in scored if m["annualized_3y"] >= top["annualized_3y"] - 0.0025]
        cheapest = min(close, key=lambda m: (m["expense_ratio"], -m["annualized_3y"]))
        return {"symbol": cheapest["symbol"], "basis": "LOWEST_OFFICIAL_EXPENSE_RATIO_AMONG_BEST_TRACKERS"}
    return {"symbol": top["symbol"], "basis": "HIGHEST_3Y_RETURN_NET_OF_COSTS"}


def build_records(*, status: dict, features: dict, research: dict, cached_bars, expense_ratio=None) -> tuple[list[dict], dict]:
    funds = [f for f in status["funds"] if f["usage"] in ("MODEL", "HELD_OUTSIDE_MODEL")]
    returns = {s: G.monthly_returns(dict(zip(f["months"], f["tr"]))) for s, f in features.items()}
    end_month = max((m for f in features.values() for m in f["months"]), default="")
    model = [f["symbol"] for f in funds if f["usage"] == "MODEL"]
    groups = G.classify_all(returns, model, end_month)
    timing = research.get("timing") or {}
    gate = research.get("gate") or {}
    records = []
    for st in funds:
        sym = st["symbol"]
        g = groups.get(sym) or {"group": "NOT_RANKED_OUTSIDE_MODEL"}
        fam = R.family_of(g["group"]) if g["group"] not in NO_CALL_GROUPS and st["usage"] == "MODEL" else None
        f = features.get(sym)
        adv = float(f["adv_63"][-1]) if f is not None and len(f["adv_63"]) and f["adv_63"][-1] == f["adv_63"][-1] else None
        rec = {"security_id": st["security_id"], "symbol": sym, "usage": st["usage"],
               "quality_status": st["quality_status"], "freshness_state": st["freshness_state"], "source_tier": 4,
               "peer_group": g["group"], "group_family": fam, "group_evidence": {k: g.get(k) for k in ("nearest_reference", "correlation", "beta_spy", "months", "flags")},
               "liquidity": _r(adv, 0), "expense_ratio": expense_ratio(sym) if expense_ratio else None,
               **(readings_from_daily(cached_bars(sym)) or readings_from_monthly(f)),
               "history_monthly": [{"month": m, "close": float(c)} for m, c in zip(f["months"][-36:], f["close"][-36:])] if f else []}
        rec.setdefault("as_of_date", st.get("as_of_date"))
        rec.setdefault("close", st.get("close"))
        records.append(rec)
    by_symbol = {r["symbol"]: r for r in records}
    by_group = defaultdict(list)
    for r in records:
        if r["usage"] == "MODEL" and r["peer_group"] not in NO_CALL_GROUPS:
            by_group[r["peer_group"]].append(r)
    group_docs = {}
    for name, members in by_group.items():
        for key in ("return_1y", "annualized_3y"):
            vals = sorted(m[key] for m in members if m.get(key) is not None)
            for m in members:
                v = m.get(key)
                m[f"{key}_group_percentile"] = None if v is None or len(vals) < 5 else round(100 * sum(x < v for x in vals) / (len(vals) - 1 or 1), 1)
        fam = R.family_of(name)
        group_docs[name] = {"members": len(members), "family": fam,
                            "median_return_1y": _r(median([m["return_1y"] for m in members if m.get("return_1y") is not None] or [math.nan])),
                            "median_annualized_3y": _r(median([m["annualized_3y"] for m in members if m.get("annualized_3y") is not None] or [math.nan])),
                            "when_to_buy": T.reading(timing.get(fam) or {}) if timing.get(fam) else None}
        for cluster in clusters([m["symbol"] for m in members], returns, end_month, cached_bars):
            best = pick_best([by_symbol[s] for s in cluster])
            for s in cluster:
                by_symbol[s]["cluster"] = {"members": cluster, "best": best.get("symbol"), "basis": best.get("basis")}
    ranking_enabled = bool(gate.get("pass_12m"))
    for r in records:
        fam = r.get("group_family")
        r["when_to_buy"] = group_docs.get(r["peer_group"], {}).get("when_to_buy")
        cl = r.get("cluster")
        if cl and cl["best"] and cl["best"] != r["symbol"]:
            r["implementation"] = {"call": "REDIRECT_NEW_MONEY", "to": cl["best"], "basis": cl["basis"]}
        elif cl and cl["best"] == r["symbol"]:
            r["implementation"] = {"call": "BEST_IN_CLUSTER", "to": None, "basis": cl["basis"]}
        else:
            r["implementation"] = {"call": "NO_NEAR_DUPLICATE", "to": None, "basis": None}
        if r["usage"] != "MODEL":
            r["ranking_call"] = "NOT_RANKED_OUTSIDE_MODEL"
        elif r["peer_group"] in NO_CALL_GROUPS:
            r["ranking_call"] = "NO_CALL_SPECIALIZED_OR_UNGROUPED"
        elif not ranking_enabled or not (gate.get("families_enabled") or {}).get(fam):
            r["ranking_call"] = "NO_VALIDATED_RANKING_EDGE"
        else:
            r["ranking_call"] = "RANKED"                       # filled by the ranking stage once a gate passes
        r["automatic_execution_authorized"] = False
    return records, group_docs
