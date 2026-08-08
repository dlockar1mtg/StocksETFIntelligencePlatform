from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.sec_historical_submission_shard_capture import (
    capture_historical_shards,
    load_json,
    sha256_bytes,
    validate_manifest,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--manifest",
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
        "--summary",
        required=True,
    )

    parser.add_argument(
        "--user-agent",
        required=True,
    )

    args = parser.parse_args()

    manifest_path = Path(
        args.manifest
    )

    manifest_bytes = (
        manifest_path.read_bytes()
    )

    manifest = load_json(
        manifest_path
    )

    authorization = load_json(
        args.authorization
    )

    expected_manifest_sha = str(
        authorization[
            "manifest_sha256"
        ]
    )

    shards = validate_manifest(
        manifest,
        expected_manifest_sha,
        manifest_bytes,
    )

    if (
        sha256_bytes(
            manifest_bytes
        )
        != expected_manifest_sha
    ):
        raise RuntimeError(
            "manifest authorization SHA mismatch"
        )

    ledger = capture_historical_shards(
        manifest,
        shards,
        authorization,
        args.raw_root,
        args.user_agent,
    )

    summary = write_outputs(
        ledger,
        args.output,
        args.summary,
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )

    return (
        0
        if ledger[
            "capture_complete"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
