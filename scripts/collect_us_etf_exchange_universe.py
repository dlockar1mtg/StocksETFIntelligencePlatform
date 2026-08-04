from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from foundation.universe.exchange_collector import (
    fetch_source,
    parse_symbol_directory,
    reconcile_candidates,
    write_collection,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect the current US exchange-listed ETF candidate universe.")
    parser.add_argument("--operating-date", default=date.today().isoformat())
    parser.add_argument("--output-root", default="data")
    args = parser.parse_args()

    policy = json.loads(Path("config/universe/us_etf_exchange_collector_policy.json").read_text(encoding="utf-8"))
    payloads = []
    parsed_candidates = []
    quarantined = []

    for source in policy["authoritative_sources"]:
        payload = fetch_source(source["source_id"], source["url"])
        payloads.append(payload)
        candidates, source_quarantine = parse_symbol_directory(payload)
        parsed_candidates.extend(candidates)
        quarantined.extend(source_quarantine)

    accepted, reconciliation_quarantine = reconcile_candidates(parsed_candidates)
    quarantined.extend(reconciliation_quarantine)
    manifest = write_collection(
        source_payloads=payloads,
        candidates=accepted,
        quarantined=quarantined,
        output_root=Path(args.output_root),
        operating_date=args.operating_date,
    )

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
