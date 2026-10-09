"""Phase 4.3: build the point-in-time official expense-ratio history for the model universe.

Usage: python scripts/run_sec_expense_ratios.py [--quarters 2025q1 2025q2 ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market import hosted_market_data as H  # noqa: E402
from foundation.market import sec_expense_ratios as X  # noqa: E402

POLICY = ROOT / "config" / "sources" / "sec_expense_ratio_policy.json"
MARKET_POLICY = ROOT / "config" / "market" / "hosted_market_data_policy.json"
CACHE = ROOT / "data" / "hosted_cache" / "sec_rr"
OUT = ROOT / "data" / "curated" / "hosted_etf"


def get(url: str, policy: dict) -> bytes:
    access = policy["sec_fair_access"]
    agent = os.environ.get(access["user_agent_environment_variable"]) or access["fallback_user_agent"]
    last = None
    for attempt in range(int(access["retry_attempts"])):
        time.sleep(float(access["minimum_seconds_between_requests"]))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": agent, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=int(access["timeout_seconds"])) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(url) from exc
            last = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"SEC download failed: {url}: {last}")


def quarters(first: str, now: datetime) -> list[str]:
    y, q = int(first[:4]), int(first[5])
    out = []
    while (y, q) <= (now.year, (now.month - 1) // 3 + 1):
        out.append(f"{y}q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarters", nargs="*")
    args = parser.parse_args(argv)
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    market = json.loads(MARKET_POLICY.read_text(encoding="utf-8"))
    universe = {f["symbol"]: f["security_id"] for f in H.load_universe(ROOT, market)}
    classes = X.class_ticker_map(json.loads(get(policy["sources"]["class_ticker_map_url"], policy)))
    wanted = {c for c, ident in classes.items() if ident["symbol"] in universe}
    now = datetime.now(timezone.utc)
    rows, report, diagnostics = [], {}, {}
    CACHE.mkdir(parents=True, exist_ok=True)
    for quarter in args.quarters or quarters(policy["sources"]["first_quarter"], now):
        path = CACHE / f"{quarter}_rr1.zip"
        url = policy["sources"]["risk_return_dataset_url_template"].format(year=quarter[:4], quarter=quarter[5])
        try:
            fresh = not path.exists()
            if fresh:
                path.write_bytes(get(url, policy))
            diag: dict = {}
            found = X.parse_quarter(path.read_bytes(), quarter, policy["tags"], wanted, diag)
            if not found and not fresh:
                # A cached archive is never refreshed otherwise; an empty one is fetched again once, in
                # case the SEC replaced a partial or reformatted file.
                path.write_bytes(get(url, policy))
                diag = {}
                found = X.parse_quarter(path.read_bytes(), quarter, policy["tags"], wanted, diag)
            rows.extend(found)
            report[quarter] = len(found)
            diagnostics[quarter] = diag
            print(f"{quarter}: {len(found)} class filings", flush=True)
            if not found:
                # 2026-10-09 (system audit): quarters 2025q3-2026q2 parsed 0 rows and nothing said so.
                print(f"::warning title=SEC {quarter} gave no expense ratios::published archive parsed to 0 class filings; "
                      f"diagnostics {json.dumps(diag)[:600]}", flush=True)
        except FileNotFoundError:
            report[quarter] = "NOT_PUBLISHED"
        except Exception as exc:  # noqa: BLE001 - a bad quarter is reported, not fatal
            report[quarter] = f"ERROR {exc}"
            print(f"{quarter}: {exc}", flush=True)
    rows = X.attach_identity(rows, classes, universe)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "expense_ratio_history.csv").write_text(X.history_csv(rows), encoding="utf-8")
    covered = sorted({r["symbol"] for r in rows if r["symbol"] in universe})
    summary = {"policy_id": policy["policy_id"], "generated_at_utc": now.replace(microsecond=0).isoformat(),
               "universe_funds": len(universe), "funds_with_sec_class": len({classes[c]["symbol"] for c in wanted}),
               "funds_with_expense_ratio": len(covered), "filings": len(rows), "quarters": report,
               "newest_filing": max((r["filed"] for r in rows if r.get("filed")), default=None),
               "empty_published_quarters": [q for q, v in report.items() if v == 0],
               "diagnostics": {q: v for q, v in diagnostics.items() if not report.get(q)},
               "without_expense_ratio": sorted(set(universe) - set(covered))}
    (OUT / "expense_ratio_summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("quarters", "without_expense_ratio")}))
    return 0 if covered else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - surface the reason in the run's annotations
        print(f"::error title=SEC expense ratios::{type(exc).__name__}: {str(exc)[:400]}")
        raise
