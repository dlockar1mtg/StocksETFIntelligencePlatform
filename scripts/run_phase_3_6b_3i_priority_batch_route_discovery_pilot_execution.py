from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_route_discovery_pilot_execution import build_summary, execute_pilot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-manifest", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--raw-directory", required=True)
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()

    pilot = json.loads(Path(args.pilot_manifest).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    output_path = Path(args.output)
    result = execute_pilot(
        pilot,
        policy,
        output_path,
        Path(args.raw_directory),
        args.user_agent,
    )
    summary = build_summary(result, output_path)
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
