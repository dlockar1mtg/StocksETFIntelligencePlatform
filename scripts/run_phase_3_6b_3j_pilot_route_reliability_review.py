from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.pilot_route_reliability_review import build_summary, review_routes, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-ledger", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    execution = json.loads(Path(args.execution_ledger).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    output_path = Path(args.output)
    review = review_routes(execution, policy)
    write_json(output_path, review)
    summary = build_summary(review, output_path)
    write_json(Path(args.summary), summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
