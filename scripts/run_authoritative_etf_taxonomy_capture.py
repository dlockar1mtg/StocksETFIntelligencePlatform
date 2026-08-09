from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_capture_runner import (
    build_execution_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--plan",
        required=True,
    )

    parser.add_argument(
        "--policy",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--summary",
        required=True,
    )

    parser.add_argument(
        "--live-network",
        action="store_true",
    )

    args = parser.parse_args()

    plan = json.loads(
        Path(args.plan).read_text(
            encoding="utf-8-sig"
        )
    )

    policy = json.loads(
        Path(args.policy).read_text(
            encoding="utf-8-sig"
        )
    )

    result = build_execution_manifest(
        plan,
        policy,
        live_network_requested=args.live_network,
    )

    output = Path(args.output)
    summary = Path(args.summary)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    summary.write_text(
        json.dumps(
            result["summary"],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            result["summary"],
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
