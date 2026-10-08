"""Hosted daily market data for the certified model universe (Phase 4.1).

Each run updates every fund's daily series (incrementally from the cached series, or in full),
reconciles the rebuilt total return with the provider's adjusted close, refuses unexplained
history rewrites, and derives month-end features for research and ranking. A fund that fails a
check keeps its last good series and is reported, never silently replaced.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from foundation.market import daily_series as S

FEATURE_FIELDS = ("security_id", "symbol", "date", "close", "tr_index", "trend_200", "vol_1y", "dd_now",
                  "maxdd_3y", "adv_63", "div_12m", "sessions")


def load_universe(root: Path, policy: dict) -> list[dict]:
    """Model-universe funds, then reference funds and held funds outside the model universe."""
    u = policy["universe"]
    doc = json.loads((root / u["model_universe_path"]).read_text(encoding="utf-8-sig"))
    records = doc["records"]
    if len(records) != int(u["required_model_population_count"]):
        raise ValueError(f"Model universe has {len(records)} records, expected {u['required_model_population_count']}")
    funds, seen = [], set()
    for r in records:
        if r.get("model_state") != "ETF_MODEL_INCLUDED":
            raise ValueError(f"{r.get('symbol')}: not ETF_MODEL_INCLUDED")
        funds.append({"security_id": r["security_id"], "symbol": r["symbol"].upper(), "usage": "MODEL"})
        seen.add(r["symbol"].upper())
    missing = [s for s in u["required_seed_symbols"] if s not in seen]
    if missing:
        raise ValueError(f"Seed symbols missing from the model universe: {missing}")
    for usage, symbols in (("STYLE_REFERENCE", u["style_reference_funds"]), ("HELD_OUTSIDE_MODEL", u["held_outside_model_universe"])):
        for s in symbols:
            if s.upper() not in seen:
                funds.append({"security_id": f"SEC-US-{s.upper()}", "symbol": s.upper(), "usage": usage})
                seen.add(s.upper())
    return funds


def _bars_from_rows(rows: list[dict]) -> list[S.Bar]:
    return [S.Bar(r["date"], float(r["close"]), None, int(r["volume"]) if r.get("volume") else None,
                  float(r["dividend"] or 0), float(r["split"] or 1), float(r["tr_index"])) for r in rows]


def update_fund(fund: dict, fetch, policy: dict, now: datetime, cache_dir: Path, *, full_refresh: bool = False) -> dict:
    """Update one fund's cached daily series. `fetch(symbol, start)` returns a chart payload."""
    symbol = fund["symbol"]
    path = cache_dir / f"{symbol}.csv"
    stored = S.read_csv(path.read_text(encoding="utf-8")) if path.exists() else []
    rules, inc = policy["reconciliation"], policy["incremental"]
    last = stored[-1]["date"] if stored else None
    stale = last is None or (now.date() - datetime.fromisoformat(last).date()).days > int(inc["full_refresh_when_stale_days"])
    # amendment 2026-10-08: a series stored at 6 decimals lost precision once its index fell below 1; rebuild it once.
    coarse = any(0 < float(r["tr_index"]) < 1 and "e" not in r["tr_index"] and len(r["tr_index"].split(".")[-1]) <= 6 for r in stored)
    mode = "FULL" if (full_refresh or stale or coarse) else "INCREMENTAL"
    failures: list[str] = []
    checks: dict = {}
    removed: list[str] = []
    jump = float(rules["implausible_daily_move"])
    bars: list[S.Bar] | None = None
    meta = {"name": "", "instrument_type": ""}
    try:
        if mode == "INCREMENTAL":
            start = datetime.fromisoformat(last).replace(tzinfo=timezone.utc) - timedelta(days=int(inc["overlap_days"]))
            parsed = S.parse_yahoo_chart(fetch(symbol, start), symbol, now_utc=now)
            meta = {"name": parsed.name, "instrument_type": parsed.instrument_type}
            known_splits = {r["date"] for r in stored if float(r["split"] or 1) != 1}
            if inc["full_refresh_when_new_split"] and any(d not in known_splits for d in parsed.splits):
                mode = "FULL"
            else:
                S.reconstruct_total_return(parsed.bars)
                checks["reconciliation"] = S.reconcile_with_provider(parsed.bars, rules)
                checks["revisions"] = S.revisions(stored[-40:], parsed.bars, {}, float(rules["revision_tolerance"]), parsed.bars[0].day)
                base = _bars_from_rows(stored)
                prev = base[-1]
                fresh = [b for b in parsed.bars if b.day > prev.day]
                for b in fresh:
                    b.tr_index = S.sig(prev.tr_index * (b.close + b.dividend) / prev.close)
                    prev = b
                bars = base + fresh
        if mode == "FULL":
            parsed = S.parse_yahoo_chart(fetch(symbol, None), symbol, now_utc=now)
            meta = {"name": parsed.name, "instrument_type": parsed.instrument_type}
            S.reconstruct_total_return(parsed.bars)
            checks["reconciliation"] = S.reconcile_with_provider(parsed.bars, rules)
            since = parsed.bars[-(int(rules["window_sessions"]) + 1)].day if len(parsed.bars) > int(rules["window_sessions"]) else parsed.bars[0].day
            # amendment 2026-10-08: only splits the stored series does not already carry rescale its closes
            # (applying every historical split quarantined 18 inverse funds on their first full refresh).
            stored_splits = {r["date"] for r in stored if float(r["split"] or 1) != 1}
            unseen = {d: r for d, r in parsed.splits.items() if d not in stored_splits}
            checks["revisions"] = (S.revisions(stored, parsed.bars, unseen, float(rules["revision_tolerance"]), since)
                                   if stored else {"changed": 0, "ok": True, "first_capture": True})
            bars = parsed.bars
        if checks["reconciliation"]["status"] != "PASS":
            failures.append("total return does not reconcile with the provider's adjusted close")
        if not checks["revisions"]["ok"]:
            failures.append("provider changed or dropped stored closes without a split")
        # A print on the last stored session can only be judged once the next session exists.
        removed += S.drop_print_errors(bars, jump, start=max(0, len(bars) - int(rules["window_sessions"]) - 1))
        checks["print_errors_removed"] = sorted(set(removed))
        recent = bars[-(int(rules["window_sessions"]) + 1):]
        jumps = [d for d in S.implausible_moves(recent, jump) if not any(b.day == d and b.split != 1 for b in recent)]
        checks["implausible_moves"] = jumps[:10]
        if jumps:
            failures.append(f"implausible daily moves on {', '.join(jumps[:3])}")
        if stored and bars[-1].day < last:
            failures.append("provider history ends before the stored history")
    except LookupError as exc:
        failures.append(str(exc))
    except Exception as exc:  # noqa: BLE001 - every fund is reported; one bad fund never stops the run
        failures.append(f"fetch/parse: {exc}")
    accepted = bars is not None and not failures
    if accepted:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(S.to_csv(bars), encoding="utf-8")
    final = bars if accepted else (_bars_from_rows(stored) if stored else [])
    quality = policy["best_quality_state_for_tier"][str(policy["provider"]["source_tier"])] if accepted else ("QUARANTINED" if stored else "BLOCKED")
    holidays = set(policy["nyse_holidays"]["dates"])
    as_of = final[-1].day if final else None
    return {
        "security_id": fund["security_id"], "symbol": symbol, "usage": fund["usage"], "mode": mode,
        "name": meta["name"], "instrument_type": meta["instrument_type"],
        "quality_status": quality, "accepted_this_run": accepted,
        "freshness_state": S.freshness_state(as_of, S.last_session(now, holidays), holidays, policy["freshness"]) if as_of else "UNKNOWN",
        "as_of_date": as_of, "first_date": final[0].day if final else None, "sessions": len(final),
        "close": final[-1].close if final else None, "failures": failures,
        "reconciliation": {k: v for k, v in (checks.get("reconciliation") or {}).items()
                           if k in ("status", "cumulative_gap_1y", "cumulative_gap_3y", "max_daily_return_gap")
                           or (k == "worst_days" and failures)},
        "print_errors_removed": checks.get("print_errors_removed") or [],
    }


def month_end_features(fund: dict, bars: list[S.Bar]) -> list[dict]:
    """Features at each completed month-end, using only data up to that day (no look-ahead)."""
    if len(bars) < 30:
        return []
    days = [b.day for b in bars]
    close = np.array([b.close for b in bars])
    tr = np.array([b.tr_index for b in bars])
    vol = np.array([b.volume or 0 for b in bars], dtype=float)
    div = np.array([b.dividend for b in bars])
    logr = np.concatenate([[0.0], np.diff(np.log(tr))])
    csum_close = np.concatenate([[0.0], np.cumsum(close)])
    csum_r, csum_r2 = np.concatenate([[0.0], np.cumsum(logr)]), np.concatenate([[0.0], np.cumsum(logr * logr)])
    csum_div = np.concatenate([[0.0], np.cumsum(div)])
    peak = np.maximum.accumulate(tr)
    dollar = close * vol
    ends = [i for i in range(len(bars) - 1) if days[i][:7] != days[i + 1][:7]]
    rows = []
    for i in ends:
        n = i + 1
        trend = close[i] / ((csum_close[n] - csum_close[n - 200]) / 200) if n >= 200 else None
        if n > 252:
            s, s2 = csum_r[n] - csum_r[n - 252], csum_r2[n] - csum_r2[n - 252]
            v = float(np.sqrt(max(s2 / 252 - (s / 252) ** 2, 0.0) * 252))
        else:
            v = None
        lo = max(0, n - 756)
        window = tr[lo:n]
        mdd = float((window / np.maximum.accumulate(window)).min() - 1)
        adv = float(np.median(dollar[max(0, n - 63):n])) if n >= 21 else None
        d12 = float(csum_div[n] - csum_div[max(0, n - 252)])
        rows.append({"security_id": fund["security_id"], "symbol": fund["symbol"], "date": days[i],
                     "close": f"{close[i]:.4f}", "tr_index": f"{tr[i]:.{S.SIGNIFICANT_DIGITS}g}",
                     "trend_200": "" if trend is None else f"{trend:.5f}", "vol_1y": "" if v is None else f"{v:.5f}",
                     "dd_now": f"{tr[i] / peak[i] - 1:.5f}", "maxdd_3y": f"{mdd:.5f}",
                     "adv_63": "" if adv is None else f"{adv:.0f}", "div_12m": f"{d12:.6f}", "sessions": n})
    return rows


def features_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FEATURE_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def read_cached_bars(cache_dir: Path, symbol: str) -> list[S.Bar]:
    path = cache_dir / f"{symbol}.csv"
    return _bars_from_rows(S.read_csv(path.read_text(encoding="utf-8"))) if path.exists() else []
