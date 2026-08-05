from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_capture_ledger_review import load_and_review


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-ledger", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--repository-root", default=".")
    args = parser.parse_args()

    summary = load_and_review(
        ledger_path=Path(args.capture_ledger),
        policy_path=Path(args.policy),
        output_path=Path(args.output),
        summary_path=Path(args.summary),
        repository_root=Path(args.repository_root),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
