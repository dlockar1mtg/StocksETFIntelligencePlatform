"""Build the daily governed UIP package from the curated series, status and research evidence.

Usage: python scripts/build_etf_package.py [--data data/curated/etf] [--output exports/etf/package]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market_data import analytics as A  # noqa: E402
from foundation.market_data import model as M  # noqa: E402
from foundation.market_data import package as P  # noqa: E402

FUNDS = ROOT / "config" / "market" / "monitored_funds.json"
MODEL = ROOT / "config" / "market" / "etf_v1_model.json"
SCHEMA = ROOT / "contracts" / "uip" / "package_manifest.schema.json"


def commit() -> str:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0000000"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "curated" / "etf")
    parser.add_argument("--output", type=Path, default=ROOT / "exports" / "etf" / "package")
    args = parser.parse_args(argv)
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
    config, model, schema = load(FUNDS), load(MODEL), load(SCHEMA)
    status = load(args.data / "market_data_status.json")
    research = load(args.data / "research" / "etf_v1_research.json")
    series = {p.stem: A.load_series(p) for p in sorted((args.data / "prices").glob("*.csv"))}
    records = M.build_records(config, model, series, status)
    manifest = P.write_package(args.output, records=records, research=research, status=status, commit=commit(),
                               generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(), schema=schema)
    P.verify_package(args.output, schema)
    print(f"{manifest['package_id']} {manifest['validation_status']} {manifest['certification_status']}")
    for r in records:
        stretch = (r.get("stretch_context") or {}).get("zone")
        print(f"  {r['ticker']:5} {r['call']:24} {r.get('redirect_to') or '':5} close {r.get('close')} "
              f"3y {r.get('annualized_3y')} stretch {stretch}")
    return 0 if manifest["validation_status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
