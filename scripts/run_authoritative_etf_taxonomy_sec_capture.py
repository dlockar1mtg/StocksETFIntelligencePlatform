from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market.authoritative_etf_taxonomy_sec_capture_launch import (
    build_launch_plan,
    execute_live,
    load_json,
    sha256_path,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--identity-manifest",
        required=True,
    )

    parser.add_argument(
        "--policy",
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

    contract = load_json(
        args.identity_manifest
    )

    policy = load_json(
        args.policy
    )

    authorization = load_json(
        args.authorization
    )

    manifest_sha = sha256_path(
        args.identity_manifest
    )

    if not args.execute_live:
        result = build_launch_plan(
            contract,
            policy,
            authorization,
            identity_manifest_sha256=
                manifest_sha,
        )

        print(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
            )
        )

        # Dry planning intentionally writes no production output.
        return 0

    if not args.user_agent:
        raise RuntimeError(
            "--user-agent is required for live execution."
        )

    result = execute_live(
        contract,
        policy,
        authorization,
        identity_manifest_sha256=
            manifest_sha,
        user_agent=
            args.user_agent,
        raw_root=
            args.raw_root,
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
