"""Phase 4.5: 3-year projections for each fund, and the walk-forward test of their calibration.

See config/market/provisional_projection_policy.json (registered before any result). A projection
is a center (typical annualized growth) plus a spread. The center comes from one of the registered
rules, chosen walk-forward by family; the spread is the fund's reference fund's own month-to-month
history, de-meaned, scaled to the fund's volatility and resampled in 12-month blocks. Everything is
point-in-time: a projection made at a month-end uses only data up to that month-end.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import median

import numpy as np

from . import provisional_ranking as R

NO_PROJECTION = ("INSUFFICIENT_HISTORY", "SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "IDIOSYNCRATIC",
                 "NOT_RANKED_OUTSIDE_MODEL")
STYLE_REFERENCE = {"US_EQUITY_LARGE_GROWTH": "VUG", "US_EQUITY_LARGE_VALUE": "VTV"}
CENTERS = ("CASH_PLUS_BETA", "REFERENCE_HISTORY", "OWN_HISTORY", "BOND_YIELD")
HORIZON = 36
MAX_BETA = 2.0          # amendment 2 (after results): beyond this a fund is not a scaled copy of its reference
MAX_VOL_SCALE = 2.5
PATHS = 2000
SEED = 20261007
# Amendment after results, 2026-10-09 (system audit): reference funds that are trusts or commodity pools
# file no SEC risk/return summary, so their official expense ratio is missing and every fund projected on
# them used to get a fee gap of 0. These issuer-published total expense ratios are used only when the SEC
# history has no value for the reference; they are not in the repo's SEC data and should be re-checked
# against the issuer pages when a prospectus changes.
REFERENCE_TRUST_FEES = {
    "SPY": 0.000945,   # State Street Global Advisors, SPDR S&P 500 ETF Trust prospectus: 0.0945%
    "GLD": 0.0040,     # SPDR Gold Trust (World Gold Trust Services) sponsor fee: 0.40%
    "SLV": 0.0050,     # BlackRock, iShares Silver Trust sponsor's fee: 0.50%
    "DBC": 0.0085,     # Invesco DB Commodity Index Tracking Fund management fee: 0.85%
    "USO": 0.0060,     # United States Commodity Funds, United States Oil Fund total expense ratio: 0.60%
}


def _months_between(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def log_returns(f: dict, end_month: str) -> dict[str, float]:
    """Monthly log total returns up to end_month, only across consecutive month-ends."""
    out = {}
    months, tr = f["months"], f["tr"]
    for k in range(1, len(months)):
        m = months[k]
        if m > end_month:
            break
        if _months_between(months[k - 1], m) == 1 and tr[k - 1] > 0 and tr[k] > 0:
            out[m] = math.log(tr[k] / tr[k - 1])
    return out


def trailing_yield(f: dict | None, end_month: str) -> float | None:
    if not f:
        return None
    i = f["index"].get(end_month)
    if i is None or i < 12:
        return None
    div, close = f["div_12m"][i], f["close"][i]
    return float(div / close) if close > 0 and div == div else None


class Projector:
    """Holds the series a projection needs and caches each reference's resampled spread."""

    def __init__(self, features: dict, expense_ratio=None, paths: int = PATHS, seed: int = SEED):
        self.f = features
        self.expense = expense_ratio or (lambda symbol, date: None)
        self.paths = paths
        self.seed = seed
        self._lr: dict[tuple[str, str], dict[str, float]] = {}
        self._spread: dict[tuple[str, str], tuple[np.ndarray, float, float]] = {}
        self.excluded: dict[str, str] = {}

    def fee(self, symbol: str, date: str) -> float | None:
        """Official expense ratio at date; for a reference trust without SEC data, the issuer's published fee."""
        value = self.expense(symbol, date)
        return REFERENCE_TRUST_FEES.get(symbol) if value is None else value

    def lr(self, symbol: str, end_month: str) -> dict[str, float]:
        key = (symbol, end_month)
        if key not in self._lr:
            self._lr[key] = log_returns(self.f[symbol], end_month) if symbol in self.f else {}
        return self._lr[key]

    def cash(self, end_month: str) -> tuple[float | None, dict[str, float]]:
        """Today's cash yield and the cash return history (BIL, SHY where BIL is too young)."""
        bil, shy = self.lr("BIL", end_month), self.lr("SHY", end_month)
        history = {**shy, **bil}
        y = trailing_yield(self.f.get("BIL"), end_month) if len(bil) >= 12 else None
        if y is None:
            y = trailing_yield(self.f.get("SHY"), end_month)
        return y, history

    def spread(self, ref: str, end_month: str) -> tuple[np.ndarray, float, float] | None:
        """(resampled 36-month sums of de-meaned reference log returns, reference mean, reference months)."""
        key = (ref, end_month)
        if key in self._spread:
            return self._spread[key]
        vals = np.array(list(self.lr(ref, end_month).values()))
        if len(vals) < 60:
            self._spread[key] = None
            return None
        mu = float(vals.mean())
        resid = vals - mu
        rng = np.random.default_rng(self.seed + sum(map(ord, ref)) + int(end_month.replace("-", "")))
        starts = rng.integers(0, len(resid) - 12 + 1, size=(self.paths, HORIZON // 12))
        sums = np.array([resid[s:s + 12].sum() for s in starts.ravel()]).reshape(self.paths, -1).sum(axis=1)
        self._spread[key] = (sums, mu, len(vals))
        return self._spread[key]

    def project(self, symbol: str, group: dict, end_month: str, center_rule: str | None = None) -> dict | None:
        name = group.get("group", "")
        if name in NO_PROJECTION or symbol not in self.f:
            return None
        ref = STYLE_REFERENCE.get(name) or group.get("nearest_reference")
        if not ref or ref not in self.f:
            return None
        sp = self.spread(ref, end_month)
        if sp is None:
            return None
        sums, ref_mu, ref_months = sp
        own, refr = self.lr(symbol, end_month), self.lr(ref, end_month)
        common = sorted(set(own) & set(refr))[-36:]
        if len(common) < 24:
            return None
        y = np.array([own[m] for m in common])
        x = np.array([refr[m] for m in common])
        scale = float(y.std() / x.std()) if x.std() > 0 else 1.0
        beta = float(np.cov(y, x, ddof=0)[0, 1] / x.var()) if x.var() > 0 else 1.0
        if beta > MAX_BETA or scale > MAX_VOL_SCALE or (group.get("beta_spy") or 0) > MAX_BETA:            # amendment 2: behaves like a leveraged or poorly matched fund
            self.excluded[symbol] = "MOVES_FAR_MORE_THAN_ITS_REFERENCE"
            return None
        self.excluded.pop(symbol, None)
        date = f"{end_month}-28"
        fee, ref_fee = self.fee(symbol, date), self.fee(ref, date)
        known = fee is not None and ref_fee is not None
        gap = (fee - ref_fee) if known else 0.0          # unknown: the center carries no fee adjustment
        cash_yield, cash_hist = self.cash(end_month)
        excess = [refr[m] - cash_hist[m] for m in refr if m in cash_hist]
        centers = {"REFERENCE_HISTORY": 12 * ref_mu - gap}
        if cash_yield is not None and len(excess) >= 60:
            centers["CASH_PLUS_BETA"] = math.log1p(cash_yield) + beta * 12 * float(np.mean(excess)) - gap
        own_vals = list(own.values())[-120:]
        if len(own_vals) >= 60:
            centers["OWN_HISTORY"] = 12 * float(np.mean(own_vals))
        family = R.family_of(name)
        fy = trailing_yield(self.f[symbol], end_month)
        if family == "BONDS" and fy is not None:
            centers["BOND_YIELD"] = math.log1p(fy)
        rule = center_rule if center_rule in centers else ("CASH_PLUS_BETA" if "CASH_PLUS_BETA" in centers else "REFERENCE_HISTORY")
        c = centers[rule]
        total = HORIZON / 12 * c + scale * sums                    # 36-month log return per path
        q = np.percentile(total, [10, 25, 50, 75, 90])
        ann = np.expm1(q * 12 / HORIZON)
        return {"center_rule": rule, "centers": {k: round(math.expm1(v), 4) for k, v in centers.items()},
                "reference": ref, "beta": round(beta, 3), "vol_scale": round(scale, 3), "fee_gap": round(gap, 5) if known else None,
                "fee_gap_status": "KNOWN" if known else "UNKNOWN",
                "p10": round(float(ann[0]), 4), "p25": round(float(ann[1]), 4), "p50": round(float(ann[2]), 4),
                "p75": round(float(ann[3]), 4), "p90": round(float(ann[4]), 4),
                "chance_of_loss": round(float(np.mean(total < 0)), 3),
                "growth_of_1000": {k: round(1000 * math.exp(float(v)), 2) for k, v in zip(("p10", "p50", "p90"), (q[0], q[2], q[4]))},
                "reference_months": int(ref_months), "family": family, "as_of_month": end_month}


def choose_rules(errors: dict[str, dict[int, dict[str, list[float]]]], start_year: int, default: str = "CASH_PLUS_BETA") -> dict[str, str]:
    """Per family, the center rule with the lowest median absolute error over starts whose 36 months had ended."""
    out = {}
    for fam, by_year in errors.items():
        seen = [y for y in by_year if y <= start_year - 3]
        if len(seen) < 3:
            out[fam] = default
            continue
        pooled = defaultdict(list)
        for y in seen:
            for rule, errs in by_year[y].items():
                pooled[rule].extend(errs)
        scored = {rule: median(e) for rule, e in pooled.items() if len(e) >= 20}
        out[fam] = min(scored, key=scored.get) if scored else default
    return out


def calibration_test(features: dict, model: list[str], groups_by_year: dict[int, dict], policy: dict, expense_ratio=None) -> dict:
    """Walk-forward: project at each December, compare with the realized 36 months."""
    pj = Projector(features, expense_ratio)
    last = max(m for f in features.values() for m in f["months"])
    years = [y for y in sorted(groups_by_year) if y >= 2005 and _months_between(f"{y}-12", last) >= HORIZON]
    errors: dict[str, dict[int, dict[str, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    obs = []
    chosen_by_year = {}
    for y in years:
        month = f"{y}-12"
        chosen = choose_rules(errors, y)
        chosen_by_year[y] = chosen
        for sym in model:
            g = groups_by_year[y].get(sym)
            f = features.get(sym)
            if not g or not f or month not in f["index"]:
                continue
            realized = R.forward(f, f["index"][month], HORIZON)
            if realized != realized:
                continue
            fam = R.family_of(g["group"])
            p = pj.project(sym, g, month, chosen.get(fam, "CASH_PLUS_BETA"))
            if p is None:
                continue
            for rule, center in p["centers"].items():
                errors[fam][y][rule].append(abs(center - realized))
            obs.append({"year": y, "symbol": sym, "family": fam, "rule": p["center_rule"], "realized": realized,
                        "p10": p["p10"], "p50": p["p50"], "p90": p["p90"],
                        "own_center": p["centers"].get("OWN_HISTORY")})
    marks = policy["test"]["pass_marks"]

    def coverage(rows):
        n = len(rows)
        if not n:
            return {"n": 0}
        inside = sum(r["p10"] <= r["realized"] <= r["p90"] for r in rows)
        return {"n": n, "inside_10_90": round(inside / n, 3),
                "below_10": round(sum(r["realized"] < r["p10"] for r in rows) / n, 3),
                "above_90": round(sum(r["realized"] > r["p90"] for r in rows) / n, 3),
                "center_median_abs_error": round(median(abs(r["p50"] - r["realized"]) for r in rows), 4),
                "own_history_median_abs_error": round(median(abs(r["own_center"] - r["realized"]) for r in rows if r["own_center"] is not None), 4)
                if any(r["own_center"] is not None for r in rows) else None}

    overall = coverage(obs)
    families = {fam: coverage([r for r in obs if r["family"] == fam]) for fam in sorted({r["family"] for r in obs})}
    by_year = {y: coverage([r for r in obs if r["year"] == y]) for y in years}
    fam_ok = all(marks["band_coverage_family_min"] <= c["inside_10_90"] <= marks["band_coverage_family_max"]
                 for c in families.values() if c["n"] >= marks["family_min_observations"])
    ok = bool(obs) and marks["band_coverage_overall_min"] <= overall["inside_10_90"] <= marks["band_coverage_overall_max"] and fam_ok
    final = choose_rules(errors, (years[-1] + 3) if years else 0)
    status = family_status(families, policy)
    return {"policy_id": policy["policy_id"], "test_starts": years, "observations": len(obs), "overall": overall,
            "families": families, "by_start_year": by_year, "rules_chosen_by_start_year": chosen_by_year,
            "rules_now": final, "passes": ok, "family_status": status}


def family_status(families: dict, policy: dict) -> dict[str, str]:
    """The 2026-10-07 amendment: each family judged on its own band."""
    marks = policy.get("family_status_marks") or {"tested_min": 0.60, "tested_max": 0.95, "min_observations": 200}
    out = {}
    for fam, c in families.items():
        if c.get("n", 0) < marks["min_observations"]:
            out[fam] = "TOO_FEW_TESTS"
        elif c["inside_10_90"] > marks["tested_max"]:
            out[fam] = "TOO_CAUTIOUS"
        elif c["inside_10_90"] < marks["tested_min"]:
            out[fam] = "TOO_NARROW"
        else:
            out[fam] = "TESTED"
    return out
