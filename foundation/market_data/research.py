"""ETF v1 research: do simple signals predict 1- and 3-year total returns, and does any new-money
timing rule beat plain monthly buying out of sample? Thresholds are chosen walk-forward."""
from __future__ import annotations

from statistics import mean, median

from foundation.market_data import analytics as A

SIGNALS = ("trend_ratio", "stretch", "drawdown", "momentum_12m")


_SIGNALS: dict[tuple[int, int, int], dict] = {}


def signal_values(s: A.Series, i: int) -> dict[str, float | None]:
    key = (id(s), len(s), i)
    if key not in _SIGNALS:
        _SIGNALS[key] = _signal_values(s, i)
    return _SIGNALS[key]


def _signal_values(s: A.Series, i: int) -> dict[str, float | None]:
    return {"trend_ratio": A.trend_ratio(s, i), "stretch": A.stretch(s, i),
            "drawdown": A.drawdown_now(s, i), "momentum_12m": A.total_return(s, A.YEAR, i)}


def signal_study(series: dict[str, A.Series]) -> dict:
    """Rank correlation between each signal at month ends and the forward 12/36-month total return."""
    out: dict = {"by_fund": {}, "pooled": {}}
    pooled: dict = {(sig, h): ([], []) for sig in SIGNALS for h in (12, 36)}
    for ticker, s in series.items():
        ends = A.month_ends(s)
        fund: dict = {}
        for h in (12, 36):
            rows = []
            for k, i in enumerate(ends):
                if k + h >= len(ends):
                    break
                fwd = s.tr[ends[k + h]] / s.tr[i] - 1
                rows.append((signal_values(s, i), fwd))
            for sig in SIGNALS:
                xs = [(v[sig], f) for v, f in rows if v[sig] is not None]
                ic = A.spearman([x for x, _ in xs], [f for _, f in xs])
                fund[f"{sig}_{h}m"] = {"rank_correlation": None if ic is None else round(ic, 3),
                                       "samples": len(xs), "independent_periods": len(xs) // h}
                pooled[(sig, h)][0].extend(x for x, _ in xs)
                pooled[(sig, h)][1].extend(f for _, f in xs)
        out["by_fund"][ticker] = fund
    for (sig, h), (xs, fs) in pooled.items():
        ic = A.spearman(xs, fs)
        out["pooled"][f"{sig}_{h}m"] = {"rank_correlation": None if ic is None else round(ic, 3), "samples": len(xs)}
    return out


def _pauses(family: str, param: float, sig: dict) -> bool:
    if family == "TREND_PAUSE":
        return sig["trend_ratio"] is not None and sig["trend_ratio"] < 1 - param
    if family == "BUY_BELOW_TREND":
        return sig["trend_ratio"] is not None and sig["trend_ratio"] > 1 + param
    if family == "STRETCH_PAUSE":
        return sig["stretch"] is not None and sig["stretch"] > param
    if family == "WAIT_FOR_DIP":
        return sig["drawdown"] > -param
    raise ValueError(family)


def simulate(fund: A.Series, cash: A.Series, start_month: str, months: int, family: str | None,
             param: float | None, contribution: float, max_wait: int) -> dict | None:
    """Monthly contributions for `months` months from start_month. family None = plain monthly buying.
    Paused money sits in the cash proxy and is invested in full when the rule allows, or after max_wait."""
    ends = [i for i in A.month_ends(fund) if fund.days[i][:7] >= start_month]
    if len(ends) < months + 1:
        return None
    ends = ends[:months + 1]
    ci = [cash.index_on_or_before(fund.days[i]) for i in ends]
    if ci[0] is None or cash.days[ci[0]][:7] != fund.days[ends[0]][:7]:
        return None
    units, held, waited, paused_months = 0.0, 0.0, 0, 0
    for k in range(months):
        i = ends[k]
        if k:
            held *= cash.tr[ci[k]] / cash.tr[ci[k - 1]]
        held += contribution
        pause = family is not None and _pauses(family, param, signal_values(fund, i))
        if pause and waited < max_wait:
            waited += 1
            paused_months += 1
            continue
        units += held / fund.tr[i]
        held, waited = 0.0, 0
    end = ends[months]
    held *= cash.tr[ci[months]] / cash.tr[ci[months - 1]]
    return {"value": units * fund.tr[end] + held, "paused_months": paused_months}


def walk_forward(series: dict[str, A.Series], cash: A.Series, config: dict) -> dict:
    months = int(config["primary_horizon_months"])
    contribution = float(config["contribution_per_month"])
    max_wait = int(config["max_wait_months"])
    first_test = config["walk_forward"]["first_test_start"]

    def month_list(s: A.Series) -> list[str]:
        return [s.days[i][:7] for i in A.month_ends(s)]

    edges: dict = {}                     # (family, param, ticker, start) -> edge vs plain monthly buying
    starts_by_fund: dict = {}
    for ticker, s in series.items():
        starts = []
        for start in month_list(s):
            base = simulate(s, cash, start, months, None, None, contribution, max_wait)
            if base is None:
                continue
            starts.append(start)
            for family, spec in config["rule_families"].items():
                for param in spec["grid"]:
                    r = simulate(s, cash, start, months, family, param, contribution, max_wait)
                    edges[(family, param, ticker, start)] = (r["value"] / base["value"] - 1, r["paused_months"])
        starts_by_fund[ticker] = starts

    def end_month(start: str) -> str:
        y, m = int(start[:4]), int(start[5:7]) + months
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        return f"{y:04d}-{m:02d}"

    report: dict = {}
    for family, spec in config["rule_families"].items():
        oos: list[tuple[str, str, float, float]] = []
        for ticker, starts in starts_by_fund.items():
            for start in starts:
                if start < first_test:
                    continue
                best, best_mean = None, None
                for param in spec["grid"]:
                    ins = [edges[(family, param, t, st)][0] for t, sts in starts_by_fund.items() for st in sts
                           if end_month(st) <= start]
                    if len(ins) < 12:
                        continue
                    m = mean(ins)
                    if best_mean is None or m > best_mean:
                        best, best_mean = param, m
                if best is None:
                    continue
                edge, paused = edges[(family, best, ticker, start)]
                oos.append((ticker, start, edge, best))
        by_fund = {}
        for ticker in starts_by_fund:
            e = [x[2] for x in oos if x[0] == ticker]
            if e:
                by_fund[ticker] = {"starts": len(e), "share_beating": round(sum(v > 0 for v in e) / len(e), 3),
                                   "median_edge": round(median(e), 4), "worst_edge": round(min(e), 4),
                                   "best_edge": round(max(e), 4)}
        all_e = [x[2] for x in oos]
        gate = config["gate"]
        passes = bool(all_e) and (
            len(all_e) >= gate["min_out_of_sample_starts"]
            and sum(v > 0 for v in all_e) / len(all_e) >= gate["min_share_of_starts_beating_baseline"]
            and median(all_e) >= gate["min_median_edge"]
            and min(all_e) >= gate["max_worst_edge"]
            and (not gate["must_hold_in_every_fund_tested"] or all(f["median_edge"] > 0 for f in by_fund.values())))
        chosen = sorted({x[3] for x in oos})
        report[family] = {
            "description": spec["description"], "out_of_sample_starts": len(all_e),
            "share_beating": None if not all_e else round(sum(v > 0 for v in all_e) / len(all_e), 3),
            "median_edge": None if not all_e else round(median(all_e), 4),
            "mean_edge": None if not all_e else round(mean(all_e), 4),
            "worst_edge": None if not all_e else round(min(all_e), 4),
            "parameters_chosen": chosen, "by_fund": by_fund, "passes_gate": passes,
            "first_test_start": min((x[1] for x in oos), default=None),
            "last_test_start": max((x[1] for x in oos), default=None),
        }
    return report


def cross_sectional_momentum(series: dict[str, A.Series], tickers: list[str], horizon: int) -> dict:
    """Among funds alive at each month end: does 12-month momentum rank the next `horizon` months?"""
    present = [series[t] for t in tickers if t in series]
    if len(present) < 3:
        return {"months": 0}
    common = sorted(set.intersection(*[set(s.days[i] for i in A.month_ends(s)) for s in present]))
    ics = []
    for k, day in enumerate(common):
        if k + horizon >= len(common):
            break
        mom, fwd = [], []
        for s in present:
            i = s.index_on_or_before(day)
            j = s.index_on_or_before(common[k + horizon])
            m = A.total_return(s, A.YEAR, i)
            if m is None:
                break
            mom.append(m)
            fwd.append(s.tr[j] / s.tr[i] - 1)
        else:
            r = A.correlation(A.rank(mom), A.rank(fwd), min_n=3) if len(set(mom)) > 1 else None
            if r is not None:
                ics.append(r)
    return {"funds": [s.ticker for s in present], "months": len(ics),
            "mean_rank_correlation": None if not ics else round(mean(ics), 3),
            "share_positive": None if not ics else round(sum(v > 0 for v in ics) / len(ics), 3)}
