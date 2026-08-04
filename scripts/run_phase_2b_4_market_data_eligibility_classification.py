from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from foundation.market.market_data_eligibility import classify_universe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    records = list(checkpoint.get("records") or [])
    result = classify_universe(
        records,
        operating_date=date.fromisoformat(args.operating_date),
        raw_root=Path(args.raw_root),
    )

    output_path = Path(args.output)
    summary_path = Path(args.summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {key: value for key, value in result.items() if key != "records"}
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
