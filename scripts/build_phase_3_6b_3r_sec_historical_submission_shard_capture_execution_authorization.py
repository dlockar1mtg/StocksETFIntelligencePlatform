from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from foundation.market.sec_historical_submission_shard_capture_execution_authorization import (
    build_authorization,
    load_json,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--manifest",
        required=True,
    )

    parser.add_argument(
        "--policy",
        required=True,
    )

    parser.add_argument(
        "--repository-root",
        default=".",
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--summary",
        required=True,
    )

    args = parser.parse_args()

    repository_root = Path(
        args.repository_root
    )

    governed_head = (
        subprocess.check_output(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            cwd=repository_root,
            text=True,
        )
        .strip()
    )

    manifest_path = Path(
        args.manifest
    )

    manifest_bytes = (
        manifest_path.read_bytes()
    )

    manifest = load_json(
        manifest_path
    )

    policy = load_json(
        args.policy
    )

    authorization = build_authorization(
        manifest,
        manifest_bytes,
        policy,
        governed_head,
    )

    write_outputs(
        authorization,
        args.output,
        args.summary,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
