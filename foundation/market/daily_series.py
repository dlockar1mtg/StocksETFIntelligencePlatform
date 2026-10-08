"""Daily ETF price series: parsing, total-return reconstruction and reconciliation.

Pure functions only (no network). The return standard (config/market/return_standard.json) is
total return with distributions reinvested at the ex-date close, so the reconstructed index moves
by (close_t + dividend_t) / close_(t-1) each session. The provider's adjusted close is reconciled
against it; provider-adjusted values are never used unreconciled.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
# The provider's adjusted close is used to reconcile each run but not stored: every new distribution
# rewrites all earlier adjusted values, while closes and the reconstructed index only ever append.
CSV_FIELDS = ("date", "close", "volume", "dividend", "split", "tr_index")


SIGNIFICANT_DIGITS = 12   # amendment 2026-10-08: a fixed 6 decimals left decayed inverse/leveraged indexes with 1-3 digits


def sig(x: float) -> float:
    """Round to significant digits, so a total-return index keeps its precision however far it falls."""
    return float(f"{x:.{SIGNIFICANT_DIGITS}g}")


class SeriesError(ValueError):
    """Raised when a provider payload cannot be turned into a governed series."""


@dataclass
class Bar:
    day: str
    close: float
    adj_close: float | None
    volume: int | None
    dividend: float = 0.0
    split: float = 1.0
    tr_index: float = 0.0


@dataclass
class ParsedSeries:
    ticker: str
    currency: str
    bars: list[Bar]
    dividends: dict[str, float] = field(default_factory=dict)
    splits: dict[str, float] = field(default_factory=dict)
    name: str = ""
    instrument_type: str = ""


def _ny_day(timestamp: int | float) -> str:
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(NEW_YORK).date().isoformat()


def parse_yahoo_chart(payload: dict, ticker: str, *, now_utc: datetime | None = None) -> ParsedSeries:
    """Turn a Yahoo v8 chart payload into daily bars. Drops today's bar until the session closes."""
    try:
        result = payload["chart"]["result"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise SeriesError(f"{ticker}: chart payload has no result") from exc
    meta = result.get("meta") or {}
    symbol = str(meta.get("symbol") or "").upper()
    if symbol and symbol != ticker.upper():
        raise SeriesError(f"{ticker}: payload is for {symbol}")
    currency = str(meta.get("currency") or "")
    if currency != "USD":
        raise SeriesError(f"{ticker}: currency {currency or 'missing'} is not USD")
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    events = result.get("events") or {}
    dividends: dict[str, float] = {}
    for item in (events.get("dividends") or {}).values():
        amount = float(item.get("amount") or 0)
        if amount > 0:
            day = _ny_day(item["date"])
            dividends[day] = round(dividends.get(day, 0.0) + amount, 6)
    splits: dict[str, float] = {}
    for item in (events.get("splits") or {}).values():
        num, den = float(item.get("numerator") or 0), float(item.get("denominator") or 0)
        if num > 0 and den > 0 and num != den:
            splits[_ny_day(item["date"])] = num / den
    now = (now_utc or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    today, settled = now.date().isoformat(), now.time() >= time(16, 30)
    by_day: dict[str, Bar] = {}
    for i, stamp in enumerate(stamps):
        close = closes[i] if i < len(closes) else None
        if close is None or round(float(close), 4) <= 0:
            continue
        day = _ny_day(stamp)
        if day > today or (day == today and not settled):
            continue                                        # no partial or future sessions
        a = adj[i] if i < len(adj) else None
        v = volumes[i] if i < len(volumes) else None
        by_day[day] = Bar(day, round(float(close), 4), None if a is None else round(float(a), 6),
                          None if v is None else int(v), dividends.get(day, 0.0), splits.get(day, 1.0))
    bars = [by_day[d] for d in sorted(by_day)]
    if not bars:
        raise SeriesError(f"{ticker}: no settled daily bars")
    name = str(meta.get("longName") or meta.get("shortName") or "")[:120]
    return ParsedSeries(ticker.upper(), currency, bars, dividends, splits, name, str(meta.get("instrumentType") or ""))


def parse_stooq_csv(text: str) -> dict[str, float]:
    """Stooq daily CSV (Date,Open,High,Low,Close,Volume) -> {date: close}. Empty if unusable."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Close" not in reader.fieldnames or "Date" not in reader.fieldnames:
        return {}
    out: dict[str, float] = {}
    for row in reader:
        try:
            close = float(row["Close"])
        except (TypeError, ValueError):
            continue
        if close > 0:
            out[str(row["Date"])] = close
    return out


def parse_nasdaq_historical(payload: dict) -> dict[str, float]:
    """Nasdaq quote-historical JSON -> {date: close}. Empty if unusable."""
    try:
        rows = payload["data"]["tradesTable"]["rows"] or []
    except (KeyError, TypeError):
        return {}
    out: dict[str, float] = {}
    for row in rows:
        try:
            month, day, year = str(row["date"]).split("/")
            close = float(str(row["close"]).replace("$", "").replace(",", ""))
        except (KeyError, ValueError):
            continue
        if close > 0:
            out[f"{year}-{month}-{day}"] = close
    return out


def reconstruct_total_return(bars: list[Bar], base: float = 100.0) -> None:
    """Fill tr_index: distributions reinvested at the ex-date close (closes are split-adjusted)."""
    level = base
    for i, bar in enumerate(bars):
        if i:
            level *= (bar.close + bar.dividend) / bars[i - 1].close
        bar.tr_index = sig(level)


def reconcile_with_provider(bars: list[Bar], rules: dict) -> dict:
    """Compare reconstructed total return with the provider's adjusted close over the window."""
    window = bars[-(int(rules["window_sessions"]) + 1):]
    usable = [b for b in window if b.adj_close]
    if len(usable) < 2 or len(usable) != len(window):
        return {"status": "FAIL", "reason": "provider adjusted close missing in the reconciliation window",
                "sessions": len(window) - 1}
    # amendment 2026-10-08: compare like with like. The provider adjusts for a distribution by scaling
    # earlier prices by (1 - d / prior close), so its ex-date return is close / (prior close - d); ours
    # reinvests at the close, (close + d) / prior close. Both come from the same closes and distributions,
    # and they differ only when a large distribution meets a large move (DFEN: 10-12% distributions, 3x),
    # so the inputs are checked in the provider's convention. The stored index keeps the return standard.
    def provider_step(prev: Bar, cur: Bar) -> float:
        if cur.dividend and prev.close > cur.dividend:
            return cur.close / (prev.close - cur.dividend)
        return (cur.close + cur.dividend) / prev.close

    level = [1.0]
    for prev, cur in zip(window, window[1:]):
        level.append(level[-1] * provider_step(prev, cur))
    worst, breaches, errors = 0.0, 0, 0
    gaps = []
    for k, (prev, cur) in enumerate(zip(window, window[1:])):
        ours = level[k + 1] / level[k] - 1
        theirs = cur.adj_close / prev.adj_close - 1
        gap = abs(ours - theirs)
        gaps.append((gap, cur))
        worst = max(worst, gap)
        breaches += gap > float(rules["daily_return_tolerance"])
        errors += gap > float(rules["daily_return_error_threshold"])

    def cumulative(n: int) -> float | None:
        # amendment 2026-10-08: relative gap. The absolute gap between growth ratios scaled with how much
        # a fund had grown, so a fund that tripled failed on the same 0.25% discrepancy a flat fund passed.
        if len(window) <= n:
            return None
        a, b = window[-n - 1], window[-1]
        return abs((level[-1] / level[-n - 1]) / (b.adj_close / a.adj_close) - 1)

    gap_1y, gap_3y = cumulative(252), cumulative(756)
    ok = (errors == 0
          and (gap_1y is None or gap_1y <= float(rules["cumulative_tolerance_1y"]))
          and (gap_3y is None or gap_3y <= float(rules["cumulative_tolerance_3y"])))
    return {"status": "PASS" if ok else "FAIL", "sessions": len(window) - 1,
            "max_daily_return_gap": round(worst, 6), "daily_gaps_over_tolerance": breaches,
            "daily_gaps_over_error_threshold": errors,
            "cumulative_gap_1y": None if gap_1y is None else round(gap_1y, 6),
            "cumulative_gap_3y": None if gap_3y is None else round(gap_3y, 6),
            "worst_days": [{"day": b.day, "gap": round(g, 6), "dividend": b.dividend, "split": b.split, "close": b.close}
                           for g, b in sorted(gaps, key=lambda t: -t[0])[:3]]}


def implausible_moves(bars: list[Bar], threshold: float) -> list[str]:
    """Sessions that look like bad prints: a move beyond the threshold that the next session undoes.

    Genuine crashes and rallies (leveraged funds on 2025-04-09, silver on 2026-01-30) are large but
    are not reversed the next day, so they stay; a spike that snaps back is a data error.
    """
    out = []
    for i in range(1, len(bars) - 1):
        prev, cur, nxt = bars[i - 1], bars[i], bars[i + 1]
        r1 = (cur.close + cur.dividend) / prev.close - 1
        if abs(r1) <= threshold:
            continue
        r2 = (nxt.close + nxt.dividend) / cur.close - 1
        if abs((1 + r1) * (1 + r2) - 1) < 0.3 * abs(r1):
            out.append(cur.day)
    return out


def drop_print_errors(bars: list[Bar], threshold: float, start: int = 0) -> list[str]:
    """Remove isolated bad prints (amendment 2026-10-08) instead of blocking the whole fund.

    A session flagged by implausible_moves is a close that the next session undoes. Removing it
    loses one day's close but no return: the move from the session before to the session after is
    carried intact, and a distribution on the removed day moves to the next session. If the bars
    carry a total-return index it is re-chained from the removal. Split days are never removed.
    Returns the removed days.
    """
    removed: list[str] = []
    while True:
        flagged = [d for d in implausible_moves(bars[start:], threshold)]
        flagged = [d for d in flagged if not any(b.day == d and b.split != 1 for b in bars)]
        if not flagged:
            return removed
        k = next(i for i, b in enumerate(bars) if b.day == flagged[0])
        bad, nxt = bars[k], bars[k + 1]
        nxt.dividend = round(nxt.dividend + bad.dividend, 6)
        del bars[k]
        removed.append(bad.day)
        if bars[k - 1].tr_index:
            for j in range(k, len(bars)):
                bars[j].tr_index = sig(bars[j - 1].tr_index * (bars[j].close + bars[j].dividend) / bars[j - 1].close)


def cross_check(bars: list[Bar], other: dict[str, float], sessions: int, tolerance: float) -> dict:
    """Latest primary closes vs an independent source on common dates."""
    if not other:
        return {"status": "UNAVAILABLE", "compared": 0}
    recent = [b for b in bars if b.day in other][-sessions:]
    if not recent:
        return {"status": "UNAVAILABLE", "compared": 0, "reason": "no common dates"}
    worst = max(abs(other[b.day] / b.close - 1) for b in recent)
    lag = sum(1 for b in bars if b.day > recent[-1].day)
    return {"status": "PASS" if worst <= tolerance else "FAIL", "compared": len(recent),
            "max_close_gap": round(worst, 6), "through": recent[-1].day, "primary_sessions_after": lag}


def revisions(old: list[dict], new: list[Bar], new_splits: dict[str, float], tolerance: float,
              since: str) -> dict:
    """Stored closes the provider has changed. Changes a new split explains are expected."""
    current = {b.day: b.close for b in new}
    changed, unexplained, missing = 0, [], []
    for row in old:
        day = row["date"]
        if day not in current:
            if day >= since:
                missing.append(day)
            continue
        factor = 1.0
        for split_day, ratio in new_splits.items():
            if split_day > day:
                factor *= ratio
        stored, now = float(row["close"]), current[day] * factor
        if abs(now / stored - 1) > tolerance:
            changed += 1
            if day >= since:
                unexplained.append(day)
    return {"changed": changed, "unexplained_recent": unexplained[:20], "missing_recent": missing[:20],
            "ok": not unexplained and not missing}


def to_csv(bars: list[Bar]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    for b in bars:
        writer.writerow([b.day, f"{b.close:.4f}",
                         "" if b.volume is None else b.volume, f"{b.dividend:g}", f"{b.split:g}", f"{b.tr_index:.{SIGNIFICANT_DIGITS}g}"])
    return buffer.getvalue()


def read_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def last_session(now_utc: datetime, holidays: set[str]) -> str:
    """Most recent fully settled NYSE session as of now (16:30 New York cut-off)."""
    now = now_utc.astimezone(NEW_YORK)
    day = now.date() if now.time() >= time(16, 30) else now.date() - timedelta(days=1)
    while day.weekday() >= 5 or day.isoformat() in holidays:
        day -= timedelta(days=1)
    return day.isoformat()


def sessions_between(start: str, end: str, holidays: set[str]) -> int:
    """Trading sessions after start up to and including end (0 if start >= end)."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    count, day = 0, a + timedelta(days=1)
    while day <= b:
        if day.weekday() < 5 and day.isoformat() not in holidays:
            count += 1
        day += timedelta(days=1)
    return count


def freshness_state(as_of: str, expected: str, holidays: set[str], rules: dict) -> str:
    behind = sessions_between(as_of, expected, holidays)
    if behind <= int(rules["current_max_sessions_behind"]):
        return "CURRENT"
    if behind <= int(rules["aging_max_sessions_behind"]):
        return "AGING"
    return "STALE"
