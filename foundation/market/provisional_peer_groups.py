"""Provisional peer groups from returns-based style analysis (Phase 4.2).

The authoritative SEC taxonomy covers 9 of the 1,077 model funds, so ranking uses a provisional
grouping that comes from each fund's own return behaviour, never from its name: the nearest
asset-class reference fund by correlation of trailing monthly total returns, checked by Sharpe
style analysis (a non-negative, fully invested mix of the references) before a fund joins a sector
or real-estate group, and refined for US equity by size/style tests. Leverage and inverse exposure
are flagged from the measured beta on the fund's near-identical twins in the universe (bonds: on
the most volatile bond reference it tracks). Groups are point-in-time: research classifies at each
December with returns up to that December, and the live package uses the same December
classification for the following year (`live_groups`). Rules amended after results on 2026-10-09
(system audit); see config/market/provisional_ranking_policy.json.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

BROAD = ("SPY", "IWM", "EFA", "EEM", "SHY", "IEF", "TLT", "LQD", "HYG", "TIP", "MUB", "GLD", "DBC", "VNQ")
CLASS_OF = {"SPY": "US_EQUITY", "IWM": "US_EQUITY", "EFA": "INTL_EQUITY", "EEM": "INTL_EQUITY", "SHY": "BONDS",
            "IEF": "BONDS", "TLT": "BONDS", "LQD": "BONDS", "HYG": "BONDS", "TIP": "BONDS", "MUB": "BONDS",
            "GLD": "PRECIOUS_METALS", "DBC": "COMMODITIES", "VNQ": "REAL_ESTATE"}
SECTORS = {"XLK": "TECHNOLOGY", "XLF": "FINANCIALS", "XLE": "ENERGY", "XLV": "HEALTH_CARE", "XLI": "INDUSTRIALS",
           "XLY": "CONSUMER_DISCRETIONARY", "XLP": "CONSUMER_STAPLES", "XLU": "UTILITIES", "XLB": "MATERIALS",
           "XLRE": "REAL_ESTATE_SECTOR", "XLC": "COMMUNICATION"}
BOND_GROUP = {"SHY": "BOND_SHORT_TREASURY", "IEF": "BOND_INTERMEDIATE_TREASURY", "TLT": "BOND_LONG_TREASURY",
              "LQD": "BOND_INVESTMENT_GRADE_CORPORATE", "HYG": "BOND_HIGH_YIELD", "TIP": "BOND_INFLATION_PROTECTED",
              "MUB": "BOND_MUNICIPAL"}
RULES = {"window_months": 36, "minimum_months": 24, "minimum_r2": 0.6, "minimum_correlation": 0.8, "defensive_beta": 0.6, "dominant_class_share": 0.6,
         "leverage_beta": 1.6, "leverage_correlation": 0.9, "inverse_correlation": -0.5, "sector_residual_correlation": 0.65,
         "small_cap_share": 0.5, "style_residual_correlation": 0.45, "sum_to_one_weight": 100.0,
         # amendment after results, 2026-10-09 (system audit): see config/market/provisional_ranking_policy.json
         "inverse_beta": -0.5, "twin_correlation": 0.975, "leverage_min_volatility": 0.10, "blend_spy_correlation": 0.99}
GROUPING_VERSION = "2026-10-09.1"     # bumped whenever the grouping rules change; published in the package


def load_month_end_tr(path: Path) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """{symbol: {YYYY-MM: tr_index}} and {symbol: security_id} from month_end_features.csv."""
    series: dict[str, dict[str, float]] = defaultdict(dict)
    ids: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            series[row["symbol"]][row["date"][:7]] = float(row["tr_index"])
            ids[row["symbol"]] = row["security_id"]
    return dict(series), ids


def monthly_returns(tr: dict[str, float]) -> dict[str, float]:
    months = sorted(tr)
    out = {}
    for prev, cur in zip(months, months[1:]):
        y, m = int(prev[:4]), int(prev[5:7])
        nxt = f"{y + (m == 12):04d}-{m % 12 + 1:02d}"
        if cur == nxt:
            out[cur] = tr[cur] / tr[prev] - 1
    return out


def style_weights(y: np.ndarray, X: np.ndarray, penalty: float) -> tuple[np.ndarray, float]:
    """Non-negative weights summing to (about) one that best explain y; returns weights and R^2."""
    A = np.vstack([X, penalty * np.ones(X.shape[1])])
    b = np.concatenate([y, [penalty]])
    w, _ = nnls(A, b)
    fit = X @ w
    ss = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(((y - fit) ** 2).sum()) / ss if ss > 0 else 0.0
    return w, r2


def _ols_beta(y: np.ndarray, x: np.ndarray) -> float:
    xc = x - x.mean()
    v = float((xc * xc).sum())
    return float((xc * (y - y.mean())).sum()) / v if v else 0.0


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


REFERENCE_GROUP = {
    "SPY": "US_EQUITY_LARGE_BLEND", "VUG": "US_EQUITY_LARGE_GROWTH", "VTV": "US_EQUITY_LARGE_VALUE",
    "IWM": "US_EQUITY_SMALL_MID", "IJH": "US_EQUITY_SMALL_MID",
    "EFA": "INTL_DEVELOPED_EQUITY", "EEM": "INTL_EMERGING_EQUITY",
    "SHY": "BOND_SHORT_TREASURY", "IEF": "BOND_INTERMEDIATE_TREASURY", "TLT": "BOND_LONG_TREASURY",
    "LQD": "BOND_INVESTMENT_GRADE_CORPORATE", "HYG": "BOND_HIGH_YIELD", "TIP": "BOND_INFLATION_PROTECTED",
    "MUB": "BOND_MUNICIPAL", "BIL": "BOND_CASH_EQUIVALENT",
    "GLD": "PRECIOUS_METALS", "SLV": "PRECIOUS_METALS", "DBC": "COMMODITIES", "USO": "COMMODITIES",
    "VNQ": "REAL_ESTATE", "XLRE": "REAL_ESTATE",
    **{k: f"US_SECTOR_{v}" for k, v in SECTORS.items() if k != "XLRE"},
}
CORE_US = ("SPY", "VUG", "VTV")
# Sector-like reference groups: a fund joins one only when the style analysis gives that group a dominant
# share of its return mix (amendment 2026-10-09). Low-volatility and dividend funds correlate with REITs,
# staples or materials through their low beta without holding mostly those stocks.
SECTOR_LIKE = {g for g in REFERENCE_GROUP.values() if g.startswith("US_SECTOR_") or g == "REAL_ESTATE"}


class TwinIndex:
    """Every fund's returns over a window, for finding a fund's near-identical exposures ("twins").

    Leverage and inverse exposure are read against the fund's twins in the whole universe as well as the
    references: a 3x semiconductor fund moves 3x SOXX and SMH, while SMH itself moves about 1x its twins.
    The 30-odd broad references alone cannot tell a naturally high-beta fund (SMH, gold miners, long zero
    coupons) from a leveraged one.
    """

    def __init__(self, returns: dict[str, dict[str, float]]):
        self.returns = returns
        self._cache: dict[tuple[str, ...], tuple] = {}

    def _matrix(self, months: list[str]):
        key = tuple(months)
        if key not in self._cache:
            syms = [s for s, r in self.returns.items() if all(m in r for m in months)]
            m = np.array([[self.returns[s][k] for k in months] for s in syms]) if syms else np.zeros((0, len(months)))
            mc = m - m.mean(axis=1, keepdims=True) if len(syms) else m
            sd = np.sqrt((mc * mc).sum(axis=1))
            # A twin that follows the S&P 500 closely (|r| >= 0.9) at under 0.75x its moves is a partial copy
            # of the market (a 40/60 allocation fund, a buffer fund), never an unlevered base.
            partial = np.zeros(len(syms), dtype=bool)
            if "SPY" in syms:
                spy = mc[syms.index("SPY")]
                vs = float((spy * spy).sum())
                if vs > 0:
                    beta = mc @ spy / vs
                    corr = np.where(sd > 0, (mc @ spy) / np.where(sd > 0, sd, 1) / np.sqrt(vs), 0.0)
                    partial = (np.abs(corr) >= 0.9) & (np.abs(beta) < 0.75)
            self._cache[key] = (syms, mc, sd, partial)
        return self._cache[key]

    def beta(self, symbol: str, y: np.ndarray, months: list[str], min_abs_corr: float) -> tuple[float | None, float | None, int]:
        """(largest |beta| on the fund's calmer twins, median signed beta on all its twins, number of twins).

        Twins are funds whose monthly returns correlate with the fund's at |r| >= min_abs_corr (0.975: a
        leveraged fund and its base correlate at 0.98-0.999, while a concentrated subset of an index, such
        as South Korea within emerging markets ex-China, sits near 0.96). Leverage is read on the calmer
        twins only: a leveraged fund moves 2-3x its calmer base, while a plain fund's leveraged versions are
        wilder and never set its reading. Direction is read on all twins: an index usually has more long
        trackers than inverse ones, so a plain fund's twins are mostly positive and an inverse fund's negative.
        """
        syms, mc, sd, partial = self._matrix(months)
        yc = y - y.mean()
        ny = float(np.sqrt((yc * yc).sum()))
        if not len(syms) or ny == 0:
            return None, None, 0
        cov = mc @ yc
        ok = sd > 0
        corr = np.where(ok, cov / np.where(ok, sd, 1) / ny, 0.0)
        mask = ok & (np.abs(corr) >= min_abs_corr) & (np.array(syms) != symbol)
        if not mask.any():
            return None, None, 0
        b = cov / np.where(ok, sd, 1) ** 2               # beta of the fund on each candidate twin
        calm = mask & (sd < ny) & ~partial
        return (float(np.max(np.abs(b[calm]))) if calm.any() else None), float(np.median(b[mask])), int(mask.sum())


def _superclass(ref: str) -> str:
    cls = CLASS_OF.get(ref)
    if cls in ("BONDS", "PRECIOUS_METALS", "COMMODITIES"):
        return cls
    if ref == "BIL":
        return "BONDS"
    if ref in ("SLV",):
        return "PRECIOUS_METALS"
    if ref in ("USO",):
        return "COMMODITIES"
    return "EQUITY"                                    # US, international, sectors and REITs


def _style_mix(y: np.ndarray, series: dict[str, np.ndarray], rules: dict) -> dict[str, float]:
    refs = list(series)
    w, _ = style_weights(y, np.column_stack([series[r] for r in refs]), float(rules["sum_to_one_weight"]))
    return dict(zip(refs, (float(v) for v in w)))


def classify(symbol: str, returns: dict[str, dict[str, float]], end_month: str, rules: dict = RULES,
             twins: TwinIndex | None = None) -> dict:
    """Peer group for one fund from the `window_months` of returns ending at end_month.

    Nearest reference by correlation decides the group; leverage and inverse exposure come from the
    fund's beta on its twins; sector and real-estate groups need a dominant style share; US large-cap
    funds are split into blend/growth/value by their residual against SPY (a fund that is SPY to
    0.99 correlation is blend), and equity funds with a low beta go to a defensive/income group.
    """
    own = returns.get(symbol, {})
    months = sorted(m for m in own if m <= end_month)[-int(rules["window_months"]):]
    refs = [r for r in REFERENCE_GROUP if all(m in returns.get(r, {}) for m in months)]
    if len(months) < int(rules["minimum_months"]) or "SPY" not in refs:
        return {"group": "INSUFFICIENT_HISTORY", "months": len(months)}
    y = np.array([own[m] for m in months])
    if y.std() == 0:
        return {"group": "INSUFFICIENT_HISTORY", "months": len(months)}
    series = {r: np.array([returns[r][m] for m in months]) for r in refs}
    corr = {r: _corr(y, x) for r, x in series.items()}
    best = max(corr, key=corr.get)
    worst = min(corr, key=corr.get)
    spy = series["SPY"]
    out = {"months": len(months), "nearest_reference": best, "correlation": round(corr[best], 3),
           "beta_spy": round(_ols_beta(y, spy), 3), "beta_nearest": round(_ols_beta(y, series[best]), 3), "flags": []}
    if symbol in REFERENCE_GROUP:                      # a reference fund defines its own group
        out["group"] = REFERENCE_GROUP[symbol]
        return out
    twin_abs, twin_beta, n_twins = (twins or TwinIndex(returns)).beta(symbol, y, months, float(rules["twin_correlation"]))
    out["twin_beta"], out["twins"] = (None if twin_beta is None else round(twin_beta, 3)), n_twins
    mirrors_reference = corr[worst] <= -0.7 and -corr[worst] > corr[best]
    inv = float(rules["inverse_beta"])
    # Against the market (beta <= -0.5) and against its twins (or, without twins, correlated below -0.5 with
    # the S&P 500): an inverse fund of an index no reference tracks (biotech). A long-duration bond with a
    # negative market beta still moves with its twins, so it is not inverse.
    against_market = out["beta_spy"] <= inv and (twin_beta <= inv if twin_beta is not None
                                                 else corr["SPY"] <= float(rules["inverse_correlation"]))
    if mirrors_reference or against_market:
        out.update(group="SPECIALIZED_INVERSE", flags=["INVERSE"])
        if mirrors_reference:
            out.update(nearest_reference=worst, correlation=round(corr[worst], 3))
        return out
    if CLASS_OF.get(best) == "BONDS" or best == "BIL":
        # Bond durations form a continuum (a 2028 Treasury ladder moves 1.9x SHY but 0.5x IEF), so a bond
        # fund is leveraged only when it moves >= 1.6x the most volatile bond reference it tracks at >= 0.9.
        # Cash (BIL) is left out: almost any bond fund moves more than 1.6x T-bills.
        tracked = [r for r in series if CLASS_OF.get(r) == "BONDS" and corr[r] >= float(rules["leverage_correlation"])]
        top = max(tracked, key=lambda r: float(series[r].std())) if tracked else None
        out["leverage_reference"] = top
        leveraged = top is not None and _ols_beta(y, series[top]) >= float(rules["leverage_beta"])
    elif twin_abs is not None:
        # no leveraged fund is calmer than 10% a year; a floating-rate note fund moves 2x a T-bill twin
        leveraged = twin_abs >= float(rules["leverage_beta"]) and float(y.std()) * 12 ** 0.5 >= float(rules["leverage_min_volatility"])
    else:                                              # no calmer twin in the universe: the reference test
        leveraged = out["beta_nearest"] >= float(rules["leverage_beta"]) and corr[best] >= float(rules["leverage_correlation"])
    if leveraged:
        inverse = twin_beta is not None and twin_beta <= inv and out["beta_spy"] < 0     # e.g. -3x China
        out.update(group="SPECIALIZED_INVERSE" if inverse else "SPECIALIZED_LEVERAGED",
                   flags=["LEVERAGED", "INVERSE"] if inverse else ["LEVERAGED"])
        return out
    if corr[best] < float(rules["minimum_correlation"]):
        out.update(group="IDIOSYNCRATIC", flags=["LOW_STYLE_FIT"])
        return out
    group = REFERENCE_GROUP[best]
    if group in SECTOR_LIKE:
        mix = _style_mix(y, series, rules)
        share = sum(v for r, v in mix.items() if REFERENCE_GROUP[r] == group)
        out["style_share"] = round(share, 3)
        if share < float(rules["dominant_class_share"]):
            # No dominant sector: a broad (non-sector) reference within the asset class that carries most
            # of the style mix (equity for a dividend fund, bonds for a low-duration bond fund).
            weight: dict[str, float] = defaultdict(float)
            for r, v in mix.items():
                weight[_superclass(r)] += v
            home = max(weight, key=weight.get)
            broad = {r: c for r, c in corr.items() if REFERENCE_GROUP[r] not in SECTOR_LIKE and _superclass(r) == home}
            if broad:
                # equity: the most correlated broad reference (the core-US split then refines it); bonds and
                # real assets: the reference with the largest style weight (a near-cash fund is cash).
                best = max(broad, key=broad.get if home == "EQUITY" else mix.get)
                group = REFERENCE_GROUP[best]
                out.update(sector_candidate=out["nearest_reference"], nearest_reference=best, correlation=round(corr[best], 3),
                           beta_nearest=round(_ols_beta(y, series[best]), 3))
    if best in CORE_US or (group == "US_EQUITY_SMALL_MID" and corr.get("SPY", 0) >= corr[best]):
        resid = y - _ols_beta(y, spy) * spy
        if corr.get("SPY", 0) >= float(rules["blend_spy_correlation"]):
            group = "US_EQUITY_LARGE_BLEND"            # the market itself, whatever its small residual tilt
        elif "VUG" in series and "VTV" in series:
            c = _corr(resid, series["VUG"] - series["VTV"])
            out["growth_value_correlation"] = round(c, 3)
            group = ("US_EQUITY_LARGE_GROWTH" if c >= float(rules["style_residual_correlation"]) else
                     "US_EQUITY_LARGE_VALUE" if c <= -float(rules["style_residual_correlation"]) else "US_EQUITY_LARGE_BLEND")
    if group.startswith("US_EQUITY") and out["beta_spy"] < float(rules["defensive_beta"]):
        group = "US_EQUITY_DEFENSIVE_INCOME"
    out["group"] = group
    return out


def classify_all(returns: dict[str, dict[str, float]], symbols: list[str], end_month: str) -> dict[str, dict]:
    twins = TwinIndex(returns)
    return {s: classify(s, returns, end_month, twins=twins) for s in symbols}


def anchor_month(end_month: str) -> str:
    """The December whose classification is live at end_month: the research sets groups each December
    and keeps them for the following year, so live groups do too (amendment 2026-10-09)."""
    return end_month if end_month[5:7] == "12" else f"{int(end_month[:4]) - 1:04d}-12"


def live_groups(returns: dict[str, dict[str, float]], symbols: list[str], end_month: str,
                previous: dict[str, dict] | None = None) -> dict[str, dict]:
    """Groups for the live package: each fund's classification at the anchor December. A fund without
    enough history then is classified on arrival (data through end_month) and keeps that group until the
    next December, when `previous` (the last package's assignments) carries it."""
    anchor = anchor_month(end_month)
    out = classify_all(returns, symbols, anchor)
    twins = TwinIndex(returns)
    for s in symbols:
        out[s]["classified_at"] = anchor
        if out[s]["group"] != "INSUFFICIENT_HISTORY":
            continue
        kept = (previous or {}).get(s) or {}
        if kept.get("group") and kept["group"] != "INSUFFICIENT_HISTORY" and anchor < str(kept.get("classified_at", "")) <= end_month:
            out[s] = dict(kept)
            continue
        g = classify(s, returns, end_month, twins=twins)
        g["classified_at"] = end_month if g["group"] != "INSUFFICIENT_HISTORY" else anchor
        out[s] = g
    return out
