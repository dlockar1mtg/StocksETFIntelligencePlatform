from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_source_acquisition import build_priority_batch_manifest, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-plan", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    batch_plan = json.loads(Path(args.batch_plan).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    result = build_priority_batch_manifest(batch_plan, policy)
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
