from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_source_route_resolution import (
    build_priority_batch_route_ledger,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sec-identities", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    sec_identities = json.loads(Path(args.sec_identities).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    result = build_priority_batch_route_ledger(manifest, sec_identities, policy)
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
