from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_controlled_source_capture_plan import (
    build_capture_plan,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-ledger", required=True)
    parser.add_argument("--reliability-review", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    route_ledger = json.loads(Path(args.route_ledger).read_text(encoding="utf-8"))
    review = json.loads(Path(args.reliability_review).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))

    plan = build_capture_plan(route_ledger, review, policy, args.operating_date)
    summary = write_outputs(plan, Path(args.output), Path(args.summary))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
