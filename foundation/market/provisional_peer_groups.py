"""Provisional peer groups from returns-based style analysis (Phase 4.2).

The authoritative SEC taxonomy covers 9 of the 1,077 model funds, so ranking uses a provisional
grouping that comes from each fund's own return behaviour, never from its name: trailing monthly
total returns are explained by a non-negative, fully invested mix of asset-class reference funds
(Sharpe style analysis), refined for US equity by sector and size/style tests. Leverage and
inverse exposure are flagged from the measured beta. Groups are recomputed point-in-time, so
research at month t only uses returns up to t.
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
         "small_cap_share": 0.5, "style_residual_correlation": 0.45, "sum_to_one_weight": 100.0}


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


def classify(symbol: str, returns: dict[str, dict[str, float]], end_month: str, rules: dict = RULES) -> dict:
    """Peer group for one fund from the `window_months` of returns ending at end_month.

    Nearest reference by correlation decides the group; leverage and inverse exposure come from the
    measured beta and correlation; US large-cap funds are split into blend/growth/value by their
    residual against SPY, and equity funds with a low beta go to a defensive/income group.
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
    if corr[worst] <= -0.7 and -corr[worst] > corr[best]:
        out.update(group="SPECIALIZED_INVERSE", flags=["INVERSE"], nearest_reference=worst, correlation=round(corr[worst], 3))
        return out
    if out["beta_nearest"] >= float(rules["leverage_beta"]) and corr[best] >= float(rules["leverage_correlation"]):
        out.update(group="SPECIALIZED_LEVERAGED", flags=["LEVERAGED"])
        return out
    if corr[best] < float(rules["minimum_correlation"]):
        out.update(group="IDIOSYNCRATIC", flags=["LOW_STYLE_FIT"])
        return out
    group = REFERENCE_GROUP[best]
    if symbol in REFERENCE_GROUP:                      # a reference fund defines its own group
        out["group"] = REFERENCE_GROUP[symbol]
        return out
    if best in CORE_US or (group == "US_EQUITY_SMALL_MID" and corr.get("SPY", 0) >= corr[best]):
        resid = y - _ols_beta(y, spy) * spy
        if "VUG" in series and "VTV" in series:
            c = _corr(resid, series["VUG"] - series["VTV"])
            out["growth_value_correlation"] = round(c, 3)
            group = ("US_EQUITY_LARGE_GROWTH" if c >= float(rules["style_residual_correlation"]) else
                     "US_EQUITY_LARGE_VALUE" if c <= -float(rules["style_residual_correlation"]) else "US_EQUITY_LARGE_BLEND")
    if group.startswith("US_EQUITY") and out["beta_spy"] < float(rules["defensive_beta"]):
        group = "US_EQUITY_DEFENSIVE_INCOME"
    out["group"] = group
    return out


def classify_all(returns: dict[str, dict[str, float]], symbols: list[str], end_month: str) -> dict[str, dict]:
    return {s: classify(s, returns, end_month) for s in symbols}
