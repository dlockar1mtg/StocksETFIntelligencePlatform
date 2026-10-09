"""Phase 4.6: research for every fund (config/market/provisional_full_coverage_policy.json, registered first).

Phase 4.5 projects only funds that are scaled copies of a reference fund. The rest get here:
  * an own-history 3-year outlook: the fund's own monthly log returns (at least 36 months), center = their
    mean, spread = the de-meaned returns resampled in 12-month blocks into 36-month paths. Leveraged and
    inverse funds' own history includes their decay. Tested walk-forward by category.
  * loose-peer cost readings (readings, never ranking calls) and, for idiosyncratic funds, the timing
    reading of the nearest reference's family, marked loose.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import median

import numpy as np

from . import provisional_peer_groups as G
from . import provisional_projection as P
from . import provisional_ranking as R

CATEGORIES = ("IDIOSYNCRATIC", "SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "MOVES_FAR_MORE_THAN_ITS_REFERENCE")
MIN_MONTHS = 36
HORIZON = 36
PATHS = 2000
SEED = 20261008


def category(group: dict, excluded: str | None) -> str | None:
    """Which Phase 4.6 category a fund is in, given its peer group and any Phase 4.5 exclusion."""
    name = (group or {}).get("group")
    if name in CATEGORIES:
        return name
    if excluded == "MOVES_FAR_MORE_THAN_ITS_REFERENCE":
        return excluded
    return None


def own_history_outlook(f: dict, end_month: str, symbol: str = "", paths: int = PATHS, seed: int = SEED) -> dict | None:
    vals = np.array(list(P.log_returns(f, end_month).values()))
    if len(vals) < MIN_MONTHS:
        return None
    mu = float(vals.mean())
    resid = vals - mu
    rng = np.random.default_rng(seed + sum(map(ord, symbol)) + int(end_month.replace("-", "")))
    starts = rng.integers(0, len(resid) - 12 + 1, size=(paths, HORIZON // 12))
    sums = resid[starts[..., None] + np.arange(12)].sum(axis=(1, 2))
    total = HORIZON * mu + sums                                  # 36-month log return per path
    q = np.percentile(total, [10, 25, 50, 75, 90])
    ann = np.expm1(q * 12 / HORIZON)
    return {"basis": "OWN_HISTORY", "months_of_history": int(len(vals)), "center": round(math.expm1(12 * mu), 4),
            "p10": round(float(ann[0]), 4), "p25": round(float(ann[1]), 4), "p50": round(float(ann[2]), 4),
            "p75": round(float(ann[3]), 4), "p90": round(float(ann[4]), 4),
            "chance_of_loss": round(float(np.mean(total < 0)), 3),
            "growth_of_1000": {k: round(1000 * math.exp(float(v)), 2) for k, v in zip(("p10", "p50", "p90"), (q[0], q[2], q[4]))},
            "as_of_month": end_month}


def status_of(c: dict, marks: dict) -> str:
    if c.get("n", 0) < marks["min_observations"]:
        return "TOO_FEW_TESTS"
    if c["inside_10_90"] > marks["tested_max"]:
        return "TOO_CAUTIOUS"
    if c["inside_10_90"] < marks["tested_min"]:
        return "TOO_NARROW"
    return "TESTED"


def calibration_test(features: dict, model: list[str], groups_by_year: dict[int, dict], policy: dict, expense_ratio=None) -> dict:
    """Every December start from 2005 whose 36 months have ended; each fund in its category at that start."""
    pj = P.Projector(features, expense_ratio)
    last = max(m for f in features.values() for m in f["months"])
    years = [y for y in sorted(groups_by_year) if y >= 2005 and P._months_between(f"{y}-12", last) >= HORIZON]
    obs = []
    for y in years:
        month = f"{y}-12"
        for sym in model:
            g = groups_by_year[y].get(sym)
            f = features.get(sym)
            if not g or not f or month not in f["index"]:
                continue
            excluded = None
            if g["group"] not in P.NO_PROJECTION and pj.project(sym, g, month) is None:
                excluded = pj.excluded.get(sym)
            cat = category(g, excluded)
            if cat is None:
                continue
            realized = R.forward(f, f["index"][month], HORIZON)
            if realized != realized:
                continue
            o = own_history_outlook(f, month, sym)
            if o is None:
                continue
            obs.append({"year": y, "symbol": sym, "category": cat, "realized": realized, "p10": o["p10"], "p50": o["p50"], "p90": o["p90"]})
    marks = policy["own_history_outlook"]["status_marks"]

    def coverage(rows):
        n = len(rows)
        if not n:
            return {"n": 0}
        return {"n": n, "funds": len({r["symbol"] for r in rows}),
                "inside_10_90": round(sum(r["p10"] <= r["realized"] <= r["p90"] for r in rows) / n, 3),
                "below_10": round(sum(r["realized"] < r["p10"] for r in rows) / n, 3),
                "above_90": round(sum(r["realized"] > r["p90"] for r in rows) / n, 3),
                "center_median_abs_error": round(median(abs(r["p50"] - r["realized"]) for r in rows), 4),
                "median_realized": round(median(r["realized"] for r in rows), 4),
                "median_center": round(median(r["p50"] for r in rows), 4)}
    cats = {c: coverage([r for r in obs if r["category"] == c]) for c in CATEGORIES}
    return {"policy_id": policy["policy_id"], "test_starts": years, "observations": len(obs), "categories": cats,
            "category_status": {c: status_of(v, marks) for c, v in cats.items()},
            "by_start_year": {y: coverage([r for r in obs if r["year"] == y]) for y in years}}


def _cost_percentile(fund: dict, peers: list[dict]) -> tuple[float | None, int]:
    priced = [p for p in peers if p.get("expense_ratio") is not None and p["symbol"] != fund["symbol"]]
    if fund.get("expense_ratio") is None or len(priced) < 4:
        return None, len(priced)
    pool = priced + [fund]
    ranks = R._rank([-p["expense_ratio"] for p in pool])        # cheaper ranks higher
    top = max(ranks) or 1.0
    return round(100 * ranks[-1] / top, 1), len(priced)


def add_full_coverage(records: list[dict], group_docs: dict, features: dict, end_month: str, research: dict | None,
                      timing_reading=None) -> dict:
    """Attach own-history outlooks, loose-peer cost readings and loose timing to the records (in place)."""
    status = (research or {}).get("category_status") or {}
    cats = (research or {}).get("categories") or {}
    by_group = defaultdict(list)
    for r in records:
        if r["usage"] == "MODEL":
            by_group[r["peer_group"]].append(r)
    counts = defaultdict(int)
    for r in records:
        cat = category({"group": r["peer_group"]}, r.get("projection_3y_excluded"))
        if cat is None or r.get("projection_3y"):
            continue
        f = features.get(r["symbol"])
        o = own_history_outlook(f, end_month, r["symbol"]) if f else None
        if o is not None:
            c = cats.get(cat) or {}
            o.update(category=cat, status=status.get(cat, "UNTESTED"), category_band_coverage=c.get("inside_10_90"),
                     category_center_median_abs_error=c.get("center_median_abs_error"), category_test_observations=c.get("n"))
            r["outlook_3y"] = o
            counts[cat] += 1
        ev = r.get("group_evidence") or {}
        if cat == "IDIOSYNCRATIC" and ev.get("nearest_reference") in G.REFERENCE_GROUP:
            loose = G.REFERENCE_GROUP[ev["nearest_reference"]]
            pct, n = _cost_percentile(r, by_group.get(loose, []))
            r["loose_peer_reading"] = {"basis": "LOOSE_PEERS", "peer_group": loose, "nearest_reference": ev["nearest_reference"],
                                       "correlation": ev.get("correlation"), "cost_percentile": pct, "priced_peers": n, "call": None}
            doc = group_docs.get(loose) or {}
            fam = R.family_of(loose)
            reading = doc.get("when_to_buy") or (timing_reading(fam) if timing_reading else None)
            # Amendment 2026-10-09: a timing rule's verdict (WAIT / BUY_NOW) speaks only for the groups its
            # family index was built from. An idiosyncratic fund (FXI, LABD) merely nearest to a real-asset
            # reference is not one of them, so it gets no rule verdict; steady buying is still shown loose.
            if reading and reading.get("rule"):
                reading = None
            if reading and not r.get("when_to_buy"):
                r["when_to_buy"] = {**reading, "loose": True, "basis": f"NEAREST_REFERENCE_FAMILY_{fam}"}
        elif cat in ("SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE"):
            pct, n = _cost_percentile(r, by_group.get(cat, []))
            r["loose_peer_reading"] = {"basis": "SAME_KIND_PEERS", "peer_group": cat, "nearest_reference": ev.get("nearest_reference"),
                                       "correlation": ev.get("correlation"), "cost_percentile": pct, "priced_peers": n, "call": None}
    return {"outlooks": dict(counts), "outlook_total": sum(counts.values())}
