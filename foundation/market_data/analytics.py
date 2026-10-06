"""ETF analytics on the curated daily series (total-return basis, 252 sessions a year)."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

YEAR = 252


@dataclass
class Series:
    ticker: str
    days: list[str]
    close: list[float]
    tr: list[float]
    dividend: list[float]

    def __len__(self) -> int:
        return len(self.days)

    def index_on_or_before(self, day: str) -> int | None:
        lo, hi = 0, len(self.days) - 1
        if not self.days or self.days[0] > day:
            return None
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.days[mid] <= day:
                lo = mid
            else:
                hi = mid - 1
        return lo


def load_series(path: Path, ticker: str | None = None) -> Series:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return Series(ticker or path.stem, [r["date"] for r in rows], [float(r["close"]) for r in rows],
                  [float(r["tr_index"]) for r in rows], [float(r["dividend"] or 0) for r in rows])


def total_return(s: Series, sessions: int, end: int | None = None) -> float | None:
    end = len(s) - 1 if end is None else end
    start = end - sessions
    return None if start < 0 else s.tr[end] / s.tr[start] - 1


def annualized(s: Series, sessions: int, end: int | None = None) -> float | None:
    r = total_return(s, sessions, end)
    return None if r is None else (1 + r) ** (YEAR / sessions) - 1


def daily_log_returns(s: Series, start: int, end: int) -> list[float]:
    return [math.log(s.tr[i] / s.tr[i - 1]) for i in range(max(start, 1), end + 1)]


def volatility(s: Series, sessions: int = 3 * YEAR, end: int | None = None) -> float | None:
    end = len(s) - 1 if end is None else end
    if end - sessions < 1:
        return None
    return pstdev(daily_log_returns(s, end - sessions + 1, end)) * math.sqrt(YEAR)


def max_drawdown(s: Series, sessions: int | None = None, end: int | None = None) -> float:
    end = len(s) - 1 if end is None else end
    start = 0 if sessions is None else max(0, end - sessions)
    peak, worst = s.tr[start], 0.0
    for v in s.tr[start:end + 1]:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def drawdown_now(s: Series, end: int | None = None) -> float:
    end = len(s) - 1 if end is None else end
    return s.tr[end] / max(s.tr[:end + 1]) - 1


def sma(values: list[float], n: int, end: int) -> float | None:
    return None if end + 1 < n else sum(values[end - n + 1:end + 1]) / n


def trend_ratio(s: Series, end: int | None = None, n: int = 200) -> float | None:
    """Close relative to its 200-session average (price basis; >1 means above trend)."""
    end = len(s) - 1 if end is None else end
    avg = sma(s.close, n, end)
    return None if avg is None else s.close[end] / avg


def stretch(s: Series, end: int | None = None, n: int = 5 * YEAR) -> float | None:
    """Total-return index relative to its own trailing five-year average."""
    end = len(s) - 1 if end is None else end
    avg = sma(s.tr, n, end)
    return None if avg is None else s.tr[end] / avg


def trailing_yield(s: Series, end: int | None = None) -> float | None:
    end = len(s) - 1 if end is None else end
    if end < YEAR:
        return None
    return sum(s.dividend[end - YEAR + 1:end + 1]) / s.close[end]


def aligned_returns(a: Series, b: Series, sessions: int) -> tuple[list[float], list[float]]:
    common = sorted(set(a.days[-sessions - 1:]) & set(b.days[-sessions - 1:]))
    ia = {d: i for i, d in enumerate(a.days)}
    ib = {d: i for i, d in enumerate(b.days)}
    ra, rb = [], []
    for prev, cur in zip(common, common[1:]):
        ra.append(a.tr[ia[cur]] / a.tr[ia[prev]] - 1)
        rb.append(b.tr[ib[cur]] / b.tr[ib[prev]] - 1)
    return ra, rb


def correlation(x: list[float], y: list[float], min_n: int = 20) -> float | None:
    if len(x) < min_n:
        return None
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    return None if not sx or not sy else sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def beta(x: list[float], market: list[float]) -> float | None:
    if len(x) < 20:
        return None
    mm = mean(market)
    var = sum((m - mm) ** 2 for m in market)
    mx = mean(x)
    return None if not var else sum((a - mx) * (m - mm) for a, m in zip(x, market)) / var


def tracking_difference(a: Series, b: Series, sessions: int = 3 * YEAR) -> float | None:
    """Annualized total-return gap a - b over the common window."""
    ra, rb = aligned_returns(a, b, sessions)
    if len(ra) < sessions * 0.9:
        return None
    ga = math.prod(1 + r for r in ra)
    gb = math.prod(1 + r for r in rb)
    years = len(ra) / YEAR
    return ga ** (1 / years) - gb ** (1 / years)


_MONTH_ENDS: dict[int, tuple[int, list[int]]] = {}


def month_ends(s: Series) -> list[int]:
    """Index of the last session of each calendar month (the final month only once it is complete)."""
    cached = _MONTH_ENDS.get(id(s))
    if cached and cached[0] == len(s):
        return cached[1]
    out = [i for i in range(len(s) - 1) if s.days[i][:7] != s.days[i + 1][:7]]
    _MONTH_ENDS[id(s)] = (len(s), out)
    return out


def rank(values: list[float]) -> list[float]:
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


def spearman(x: list[float], y: list[float]) -> float | None:
    return correlation(rank(x), rank(y)) if len(x) >= 20 else None
