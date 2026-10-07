from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market.corrected_sec_route_discovery_pilot_execution_authorization import (
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
        "--governed-head",
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

    policy = load_json(
        args.policy
    )

    authorization = build_authorization(
        manifest,
        manifest_bytes,
        policy,
        args.governed_head,
    )

    write_outputs(
        authorization,
        Path(args.output),
        Path(args.summary),
    )

    print("=" * 72)
    print(
        "Corrected SEC Route-Discovery "
        "Pilot Execution Authorization"
    )
    print("=" * 72)

    print(
        "Authorized records:             "
        f"{authorization['authorized_record_count']}"
    )

    print(
        "Authorized symbols:             "
        + ", ".join(
            authorization[
                "authorized_symbols"
            ]
        )
    )

    print(
        "Candidate documents/security:   "
        f"{authorization['execution_contract']['maximum_candidate_documents_per_security']}"
    )

    print(
        "Maximum total SEC requests:     "
        f"{authorization['execution_contract']['maximum_total_sec_requests']}"
    )

    print(
        "Maximum requests/second:        "
        f"{authorization['execution_contract']['maximum_requests_per_second']}"
    )

    print(
        "Network capture authorized:     True"
    )

    print(
        "Automatic execution authorized: False"
    )

    print(
        "Full 215 execution authorized:  False"
    )

    print(
        "Taxonomy normalization:         False"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
