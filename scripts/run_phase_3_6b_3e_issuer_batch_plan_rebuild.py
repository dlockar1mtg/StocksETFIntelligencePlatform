from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.issuer_batch_plan_rebuild import build_issuer_batch_plan, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issuer-ledger", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    ledger = json.loads(Path(args.issuer_ledger).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    result = build_issuer_batch_plan(ledger, policy)
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({key: value for key, value in result.items() if key not in {"records", "batches"}}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
