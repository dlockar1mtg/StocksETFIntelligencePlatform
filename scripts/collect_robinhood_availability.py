from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.universe.robinhood_collector import collect_availability


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-root", default="data")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    args = parser.parse_args()

    candidates = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    policy = json.loads(Path("config/brokers/robinhood_availability_collector_policy.json").read_text(encoding="utf-8"))
    manifest = collect_availability(
        candidates,
        output_root=Path(args.output_root),
        operating_date=args.operating_date,
        url_template=policy["lookup_url_template"],
        minimum_delay_seconds=args.delay_seconds,
        checkpoint_every_records=policy["checkpoint_every_records"],
        max_records=args.max_records,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
