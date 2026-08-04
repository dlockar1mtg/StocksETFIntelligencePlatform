from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_route_discovery_pilot import (
    build_route_discovery_pilot,
    write_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-ledger", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    route_ledger = json.loads(Path(args.route_ledger).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    result = build_route_discovery_pilot(route_ledger, policy)
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
