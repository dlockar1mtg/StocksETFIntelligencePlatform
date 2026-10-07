from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

if str(
    ROOT
) not in sys.path:
    sys.path.insert(
        0,
        str(
            ROOT
        ),
    )

from foundation.market.authoritative_etf_taxonomy_historical_metadata_capture import (
    build_offline_plan,
    capture_historical_metadata,
    load_json,
    sha256_path,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--plan",
        required=True,
    )

    parser.add_argument(
        "--authorization",
        required=True,
    )

    parser.add_argument(
        "--raw-root",
        required=True,
    )

    parser.add_argument(
        "--checkpoint",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--user-agent",
    )

    parser.add_argument(
        "--execute-live",
        action="store_true",
    )

    args = parser.parse_args()

    plan = load_json(
        args.plan
    )

    authorization = load_json(
        args.authorization
    )

    plan_sha = sha256_path(
        args.plan
    )

    if not args.execute_live:
        result = build_offline_plan(
            plan,
            authorization,
            plan_sha256=
                plan_sha,
        )

        print(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
            )
        )

        return 0

    if not args.user_agent:
        raise RuntimeError(
            "--user-agent is required for live execution."
        )

    result = capture_historical_metadata(
        plan,
        authorization,
        plan_sha256=
            plan_sha,
        raw_root=
            args.raw_root,
        checkpoint_path=
            args.checkpoint,
        user_agent=
            args.user_agent,
    )

    output = Path(
        args.output
    )

    output.parent.mkdir(
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

    print(
        json.dumps(
            {
                key: value
                for key, value
                in result.items()
                if key != "records"
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
