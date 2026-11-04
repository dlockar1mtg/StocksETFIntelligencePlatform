"""Collect daily closes, distributions and splits for the monitored ETFs (config/market/monitored_funds.json).

Runs in GitHub Actions (the sources are not reachable from every network). For each fund:
  1. fetch the full daily history from the primary provider (Yahoo chart v8),
  2. rebuild total return (distributions reinvested at the ex-date close) and reconcile it with the
     provider's adjusted close over the last three years,
  3. reject implausible moves, cross-check the latest closes against Stooq, and compare with the
     stored series so a provider rewrite of history is never accepted silently,
  4. write the curated series and a status record per fund (a governed observation).
A fund that fails a check is quarantined: its stored series is kept and the new one is set aside.
Free sources are tier 4, so the best quality state is PROVISIONAL, never PASS (certified).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market_data import series as S  # noqa: E402

CONFIG = ROOT / "config" / "market" / "monitored_funds.json"
STORE = ROOT / "data" / "curated" / "etf"
QUARANTINE = ROOT / "data" / "quarantine" / "etf"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) StocksETFIntelligencePlatform/1.0 (personal research)"
YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")


def http_get(url: str, attempts: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url.split('?')[0]}: {last}")


def fetch_yahoo(ticker: str, now: datetime) -> dict:
    errors = []
    for host in YAHOO_HOSTS:
        url = (f"https://{host}/v8/finance/chart/{ticker}?period1=0&period2={int(now.timestamp())}"
               "&interval=1d&events=div%2Csplit&includeAdjustedClose=true")
        try:
            return json.loads(http_get(url))
        except Exception as exc:  # noqa: BLE001 - try the next host, report all failures
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def fetch_cross_check(fund: dict, now: datetime | None = None) -> tuple[str, dict[str, float]]:
    """Independent closes: Stooq first, then Nasdaq. Returns (provider_id, closes); empty if neither answers."""
    try:
        closes = S.parse_stooq_csv(http_get(f"https://stooq.com/q/d/l/?s={fund['stooq_symbol']}&i=d", attempts=2).decode("utf-8", "replace"))
        if closes:
            return "STOOQ_DAILY_CSV", closes
    except Exception:  # noqa: BLE001 - the cross-check is optional; absence is recorded as a limitation
        pass
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=21)).date().isoformat()
    url = (f"https://api.nasdaq.com/api/quote/{fund['ticker']}/historical?assetclass=etf"
           f"&fromdate={start}&todate={now.date().isoformat()}&limit=30")
    try:
        closes = S.parse_nasdaq_historical(json.loads(http_get(url, attempts=2)))
        if closes:
            return "NASDAQ_QUOTE_HISTORICAL", closes
    except Exception:  # noqa: BLE001
        pass
    return "", {}


def process_fund(fund: dict, provider: dict, rules: dict, fresh_rules: dict, holidays: set[str], now: datetime,
                 store: Path, output: Path, quarantine: Path, *, yahoo=fetch_yahoo, stooq=fetch_cross_check) -> dict:
    ticker = fund["ticker"]
    path, out_path = store / "prices" / f"{ticker}.csv", output / "prices" / f"{ticker}.csv"
    stored_text = path.read_text(encoding="utf-8") if path.exists() else ""
    stored = S.read_csv(stored_text) if stored_text else []
    expected = S.last_session(now, holidays)
    limitations: list[str] = ["Tier 4 public source: provisional, not certified."]
    checks: dict = {}
    failures: list[str] = []
    try:
        parsed = S.parse_yahoo_chart(yahoo(ticker, now), ticker, now_utc=now)
    except Exception as exc:  # noqa: BLE001
        parsed = None
        failures.append(f"fetch: {exc}")
    if parsed is not None:
        S.reconstruct_total_return(parsed.bars)
        checks["reconciliation"] = S.reconcile_with_provider(parsed.bars, rules)
        if checks["reconciliation"]["status"] != "PASS":
            failures.append("reconstructed total return does not reconcile with the provider's adjusted close")
        recent = parsed.bars[-(int(rules["window_sessions"]) + 1):]
        jumps = [d for d in S.implausible_moves(recent, float(rules["implausible_daily_move"])) if d not in parsed.splits]
        checks["implausible_moves"] = jumps
        if jumps:
            failures.append(f"implausible daily moves on {', '.join(jumps[:5])}")
        source, other = stooq(fund)
        checks["cross_check"] = {**S.cross_check(parsed.bars, other, int(rules["cross_check_sessions"]),
                                                 float(rules["cross_check_tolerance"])), "provider_id": source or None}
        if checks["cross_check"]["status"] == "FAIL":
            failures.append("latest closes disagree with the independent cross-check source")
        elif checks["cross_check"]["status"] == "UNAVAILABLE":
            limitations.append("Independent cross-check source unavailable this run; single-source closes.")
        since = parsed.bars[-(int(rules["window_sessions"]) + 1)].day
        checks["revisions"] = S.revisions(stored, parsed.bars, parsed.splits, float(rules["revision_tolerance"]), since) if stored else {"changed": 0, "ok": True, "first_capture": True}
        if not checks["revisions"]["ok"]:
            failures.append("provider changed or dropped stored closes from the last three years without a split")
        if stored and parsed.bars[-1].day < stored[-1]["date"]:
            failures.append("provider history ends before the stored history")
    accepted = parsed is not None and not failures
    if accepted:
        text = S.to_csv(parsed.bars)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        quality = provider["best_quality"]
    else:
        text = stored_text
        if parsed is not None:
            quarantine.mkdir(parents=True, exist_ok=True)
            (quarantine / f"{ticker}.csv").write_text(S.to_csv(parsed.bars), encoding="utf-8")
        if stored_text and out_path != path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(stored_text, encoding="utf-8")
        quality = "QUARANTINED" if text else "BLOCKED"
    rows = S.read_csv(text) if text else []
    last = rows[-1] if rows else None
    as_of = last["date"] if last else None
    observed = f"{as_of}T21:00:00+00:00" if as_of else now.isoformat()
    observed = min(observed, now.isoformat())
    dividends_12m = [r for r in rows if as_of and r["date"] > f"{int(as_of[:4]) - 1}{as_of[4:]}" and float(r["dividend"] or 0) > 0]
    return {
        "security_id": fund["security_id"], "ticker": ticker, "name": fund["name"], "role": fund["role"],
        "usage": fund["usage"], "index": fund["index"], "domain": "adjusted_price",
        "provider_id": provider["provider_id"], "provider_version": provider["provider_version"],
        "source_tier": provider["source_tier"], "license_class": provider["license_class"],
        "supported_domains": provider["supported_domains"], "source_record_id": f"{provider['provider_id']}:{ticker}:{as_of}",
        "observed_at_utc": observed, "retrieved_at_utc": now.isoformat(), "as_of_date": as_of,
        "content_sha256": S.sha256_text(text) if text else "0" * 64,
        "quality_status": quality,
        "freshness_state": S.freshness_state(as_of, expected, holidays, fresh_rules) if as_of else "UNKNOWN",
        "accepted_this_run": accepted, "failures": failures, "limitations": limitations, "checks": checks,
        "payload": {
            "first_date": rows[0]["date"] if rows else None, "sessions": len(rows),
            "last_close": float(last["close"]) if last else None,
            "last_tr_index": float(last["tr_index"]) if last else None,
            "distributions_trailing_12m": round(sum(float(r["dividend"]) for r in dividends_12m), 6),
            "distribution_count_trailing_12m": len(dividends_12m),
            "series_path": f"prices/{ticker}.csv",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE, help="where the stored curated series live")
    parser.add_argument("--output", type=Path, default=None, help="where to write (default: the store)")
    parser.add_argument("--quarantine", type=Path, default=QUARANTINE)
    parser.add_argument("--only", nargs="*", help="limit to these tickers")
    args = parser.parse_args(argv)
    output = args.output or args.store
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    primary = next(p for p in config["providers"] if p["role"] == "PRIMARY")
    primary = {**primary, "best_quality": config["best_quality_state_for_tier"][str(primary["source_tier"])]}
    holidays = set(config["nyse_holidays"]["dates"])
    now = datetime.now(timezone.utc).replace(microsecond=0)
    funds = [f for f in config["funds"] if not args.only or f["ticker"] in args.only]
    records = []
    for fund in funds:
        record = process_fund(fund, primary, config["reconciliation"], config["freshness"], holidays, now,
                              args.store, output, args.quarantine)
        records.append(record)
        print(f"{record['ticker']:5} {record['quality_status']:12} {record['freshness_state']:8} as of {record['as_of_date']} "
              f"close {record['payload']['last_close']} {'; '.join(record['failures'])}")
    status = {
        "status_version": "1.0.0", "policy_id": config["policy_id"], "generated_at_utc": now.isoformat(),
        "expected_session": S.last_session(now, holidays),
        "funds": records,
        "summary": {state: sum(1 for r in records if r["quality_status"] == state)
                    for state in ("PASS", "PROVISIONAL", "QUARANTINED", "BLOCKED")},
        "certified_market_monitoring_authorized": False, "automatic_execution_authorized": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "market_data_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    held = [r for r in records if r["usage"] == "HELD"]
    if held and all(r["quality_status"] == "BLOCKED" for r in held):
        print("No held fund has any usable data.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
