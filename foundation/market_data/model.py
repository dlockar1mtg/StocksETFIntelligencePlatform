"""ETF v1: readings and new-money guidance for each held fund.

Research (October 2026, daily total return since each fund's start, SPY from 1993): no timing rule
for new money (pause below trend, buy only below trend, pause when stretched, wait for a dip) beat
plain monthly buying out of sample over three years; most lost. Stretch (the total-return index
against its own five-year average) did rank later returns (rank correlation -0.23 at three years,
pooled): the most stretched fifth of months was followed by lower three-year returns, but still
mostly above cash, so pausing did not pay. The guidance is therefore steady monthly buying, with
stretch shown as context, and the actionable advice is structural: where two held funds are the
same exposure, new money goes to the cheaper one that tracked at least as well.
"""
from __future__ import annotations

from statistics import median

from foundation.market_data import analytics as A

MODEL_VERSION = "etf-v1"
CALLS = {"STEADY": "STEADY_ACCUMULATION", "REDIRECT": "REDIRECT_NEW_MONEY", "NO_DATA": "NO_CURRENT_MARKET_PRICE"}


def stretch_context(proxy: A.Series, current: float | None) -> dict | None:
    """Where today's stretch sits in the proxy's own history, and what followed similar readings."""
    if current is None:
        return None
    ends = A.month_ends(proxy)
    samples = []
    for k, i in enumerate(ends):
        st = A.stretch(proxy, i)
        if st is None:
            continue
        fwd = (proxy.tr[ends[k + 36]] / proxy.tr[i]) ** (1 / 3) - 1 if k + 36 < len(ends) else None
        samples.append((st, fwd))
    if len(samples) < 60:
        return None
    values = sorted(st for st, _ in samples)
    pct = sum(1 for v in values if v < current) / len(values)
    done = sorted((st, f) for st, f in samples if f is not None)
    n = len(done)
    fifths = [done[j * n // 5:(j + 1) * n // 5] for j in range(5)]
    band = next((j for j, b in enumerate(fifths) if b and current <= b[-1][0]), 4)
    zone = "STRETCHED" if pct >= 0.85 else "ELEVATED" if pct >= 0.6 else "NORMAL" if pct >= 0.25 else "DEPRESSED"
    return {"stretch": round(current, 4), "percentile": round(pct, 3), "zone": zone, "proxy": proxy.ticker,
            "history_from": proxy.days[0], "band": band + 1,
            "forward_3y_median_in_band": round(median(f for _, f in fifths[band]), 4),
            "forward_3y_median_all": round(median(f for _, f in done), 4),
            "bands": [{"band": j + 1, "stretch_from": round(b[0][0], 3), "stretch_to": round(b[-1][0], 3),
                       "forward_3y_median": round(median(f for _, f in b), 4), "samples": len(b)} for j, b in enumerate(fifths) if b]}


def fund_reading(fund: dict, s: A.Series, proxy: A.Series, voo: A.Series | None, status: dict) -> dict:
    ra, rv = A.aligned_returns(s, voo, 756) if voo is not None and voo is not s else ([], [])

    def r(x, places=4):
        return None if x is None else round(x, places)

    monthly = [{"month": s.days[i][:7], "close": s.close[i], "tr_index": round(s.tr[i], 4)} for i in A.month_ends(s)][-120:]
    daily = [{"date": d, "close": c} for d, c in zip(s.days[-252:], s.close[-252:])]
    return {
        "as_of_date": s.days[-1], "close": s.close[-1],
        "return_1m": r(A.total_return(s, 21)), "return_3m": r(A.total_return(s, 63)),
        "return_1y": r(A.total_return(s, A.YEAR)), "annualized_3y": r(A.annualized(s, 3 * A.YEAR)),
        "annualized_5y": r(A.annualized(s, 5 * A.YEAR)),
        "annualized_since_start": r((s.tr[-1] / s.tr[0]) ** (A.YEAR / max(1, len(s) - 1)) - 1),
        "history_from": s.days[0],
        "volatility_3y": r(A.volatility(s)), "max_drawdown_3y": r(A.max_drawdown(s, 3 * A.YEAR)),
        "max_drawdown_all": r(A.max_drawdown(s)), "drawdown_now": r(A.drawdown_now(s)),
        "trend_ratio_200d": r(A.trend_ratio(s)),
        "trend_state": None if A.trend_ratio(s) is None else ("ABOVE" if A.trend_ratio(s) >= 1 else "BELOW"),
        "trailing_yield": r(A.trailing_yield(s)),
        "distributions_12m": status.get("payload", {}).get("distributions_trailing_12m"),
        "correlation_vs_voo_3y": r(A.correlation(ra, rv)) if ra else (1.0 if voo is s else None),
        "beta_vs_voo_3y": r(A.beta(ra, rv)) if ra else (1.0 if voo is s else None),
        "stretch_context": stretch_context(proxy, A.stretch(proxy)),
        "history_monthly": monthly, "history_daily": daily,
    }


def overlaps(held: dict[str, A.Series], funds: dict[str, dict], structure: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {t: [] for t in held}
    tickers = sorted(held)
    for a in tickers:
        for b in tickers:
            if a == b:
                continue
            ra, rb = A.aligned_returns(held[a], held[b], 756)
            corr = A.correlation(ra, rb)
            if corr is None or corr < 0.9:
                continue
            out[a].append({"ticker": b, "correlation_3y": round(corr, 4),
                           "same_index": funds[a]["index"] == funds[b]["index"],
                           "tracking_difference_3y": None if (td := A.tracking_difference(held[a], held[b])) is None else round(td, 4),
                           "expense_ratio": structure["expense_ratios"].get(b)})
        out[a].sort(key=lambda o: -o["correlation_3y"])
    return out


def guidance(ticker: str, fund_overlaps: list[dict], structure: dict) -> dict:
    """Redirect new money when another held fund is the same exposure, cheaper, and tracked at least as well."""
    fee = structure["expense_ratios"].get(ticker)
    best = None
    for o in fund_overlaps:
        same = o["same_index"] or o["correlation_3y"] >= structure["same_index_correlation"]
        cheaper = fee is not None and o["expense_ratio"] is not None and o["expense_ratio"] < fee
        as_well = o["tracking_difference_3y"] is not None and o["tracking_difference_3y"] <= 0
        if same and cheaper and as_well and (best is None or o["expense_ratio"] < best["expense_ratio"]):
            best = o
    if best:
        why = "tracks the same index" if best["same_index"] else f"moved almost identically ({best['correlation_3y']:.3f} correlation over 3 years)"
        return {"call": "REDIRECT", "redirect_to": best["ticker"],
                "reason": f"{best['ticker']} {why}, costs {best['expense_ratio'] * 100:.2f}% a year against "
                          f"{fee * 100:.2f}%, and returned {-best['tracking_difference_3y'] * 100:.2f}% a year more over 3 years. "
                          f"New money goes further in {best['ticker']}; shares you already hold can stay."}
    return {"call": "STEADY", "redirect_to": None,
            "reason": "No timing rule beat plain monthly buying over 3 years in testing, so the guidance is to keep buying steadily."}


def build_records(config: dict, model: dict, series: dict[str, A.Series], status: dict) -> list[dict]:
    funds = {f["ticker"]: f for f in config["funds"]}
    by_status = {f["ticker"]: f for f in status["funds"]}
    held_tickers = [f["ticker"] for f in config["funds"] if f["usage"] == "HELD"]
    held = {t: series[t] for t in held_tickers if t in series}
    structure = model["structure"]
    over = overlaps(held, funds, structure)
    voo = series.get("VOO")
    records = []
    for t in held_tickers:
        fund, st = funds[t], by_status.get(t, {})
        base = {"security_id": fund["security_id"], "ticker": t, "name": fund["name"], "issuer": fund["issuer"],
                "role": fund["role"], "index": fund["index"], "expense_ratio": structure["expense_ratios"].get(t),
                "quality_status": st.get("quality_status", "BLOCKED"), "freshness_state": st.get("freshness_state", "UNKNOWN"),
                "source_tier": st.get("source_tier"), "provider_id": st.get("provider_id"),
                "limitations": st.get("limitations", []), "model_version": MODEL_VERSION}
        if t not in series or base["quality_status"] == "BLOCKED":
            records.append({**base, "call": CALLS["NO_DATA"], "call_reason": "No usable market data this run."})
            continue
        proxy = series.get(model["research_proxies"].get(t, t), series[t])
        g = guidance(t, over.get(t, []), structure)
        records.append({**base, **fund_reading(fund, series[t], proxy, voo, st), "overlaps": over.get(t, []),
                        "call": CALLS[g["call"]], "redirect_to": g["redirect_to"], "call_reason": g["reason"]})
    return records
