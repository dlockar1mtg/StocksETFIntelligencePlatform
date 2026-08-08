from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from foundation.market.sec_series_class_resolution_pilot_execution_authorization import (
    build_authorization,
    load_json,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--resolution-policy", required=True)
    parser.add_argument("--authorization-policy", required=True)
    parser.add_argument("--governed-head", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)

    args = parser.parse_args()

    resolution_policy_path = Path(
        args.resolution_policy
    )

    resolution_policy_bytes = (
        resolution_policy_path.read_bytes()
    )

    resolution_policy = load_json(
        resolution_policy_path
    )

    authorization_policy = load_json(
        args.authorization_policy
    )

    authorization = build_authorization(
        resolution_policy,
        resolution_policy_bytes,
        authorization_policy,
        args.governed_head,
    )

    write_outputs(
        authorization,
        Path(args.output),
        Path(args.summary),
    )

    print("=" * 72)
    print(
        "SEC Series/Class Resolution "
        "Pilot Execution Authorization"
    )
    print("=" * 72)

    print(
        "Authorized records:           "
        f"{authorization['authorized_record_count']}"
    )

    print(
        "Authorized symbols:           "
        + ", ".join(authorization["authorized_symbols"])
    )

    contract = authorization["execution_contract"]

    print(
        "Recent filings:               "
        f"{contract['maximum_recent_filings_scanned']}"
    )

    print(
        "Documents per filing:         "
        f"{contract['maximum_documents_per_filing']}"
    )

    print(
        "Maximum SEC requests:         "
        f"{contract['maximum_total_sec_requests']}"
    )

    print(
        "Maximum requests/second:      "
        f"{contract['maximum_requests_per_second']}"
    )

    print(
        "Retries:                      "
        f"{contract['maximum_retry_attempts']}"
    )

    print("Network capture authorized:   True")
    print("Automatic execution:          False")
    print("Full 215 execution:           False")
    print("Taxonomy normalization:       False")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
