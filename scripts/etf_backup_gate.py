"""Backup-run gate for the hosted ETF workflow: is the committed status already current?

Usage: python scripts/etf_backup_gate.py STATUS_JSON [--now 2026-10-09T01:20:00Z]

Prints `run=false` when at least MIN_CURRENT_SHARE of the funds in the status file have an as_of_date
equal to the last completed US session at run time (weekends and NYSE holidays from the market data
policy), else `run=true`. It never trusts the stored freshness labels: those were computed when the
status was written, so a status written before a session closed still says CURRENT afterwards
(amendment 2026-10-09, system audit). Standard library only: the gate job installs nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market import daily_series as S  # noqa: E402

POLICY = ROOT / "config" / "market" / "hosted_market_data_policy.json"
MIN_CURRENT_SHARE = 0.9


def current_share(status: dict, session: str) -> float:
    funds = status.get("funds") or []
    if not funds:
        return 0.0
    return sum(1 for f in funds if f.get("as_of_date") == session) / len(funds)


def decide(status: dict, now: datetime, holidays: set[str]) -> tuple[bool, str, float]:
    """(run?, the last completed session, share of funds on it)."""
    session = S.last_session(now, holidays)
    share = current_share(status, session)
    return share < MIN_CURRENT_SHARE, session, share


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("status", type=Path)
    parser.add_argument("--now", help="ISO time (default: now, UTC)")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    holidays = set(json.loads(POLICY.read_text(encoding="utf-8"))["nyse_holidays"]["dates"])
    try:
        status = json.loads(args.status.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:          # unreadable status: collect
        print(f"::notice title=Backup run::status unreadable ({exc}); collecting")
        print("run=true")
        return 0
    run, session, share = decide(status, now, holidays)
    verb = "collecting again" if run else "skipping"
    print(f"::notice title=Backup run::{share:.1%} of {len(status.get('funds') or [])} funds are on {session}, "
          f"the last completed session (need {MIN_CURRENT_SHARE:.0%}); {verb}")
    print(f"run={'true' if run else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
