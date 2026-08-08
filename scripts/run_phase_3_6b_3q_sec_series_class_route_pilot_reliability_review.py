from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.sec_series_class_route_pilot_reliability_review import (
    analyze_unresolved_gap,
    build_review_ledger,
    load_json,
    review_resolved_record,
    sha256_bytes,
    validate_accession_reuse,
    validate_resolution_contract,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--resolution-ledger",
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

    ledger_path = Path(
        args.resolution_ledger
    )

    resolution = load_json(
        ledger_path
    )

    policy = load_json(
        args.policy
    )

    records = (
        validate_resolution_contract(
            ledger_path,
            resolution,
            policy,
        )
    )

    by_symbol = {
        str(
            record[
                "symbol"
            ]
        ): record
        for record in records
    }

    review_policy = policy[
        "review"
    ]

    resolved_reviews = [
        review_resolved_record(
            by_symbol[
                symbol
            ],
            args.repository_root,
            list(
                policy[
                    "required_identity_markers"
                ]
            ),
            require_structured_association=bool(
                review_policy[
                    "require_structured_series_class_ticker_association"
                ]
            ),
            require_index_header=bool(
                review_policy[
                    "require_index_header_for_structured_resolution"
                ]
            ),
        )
        for symbol in policy[
            "required_resolved_symbols"
        ]
    ]

    unresolved_reviews = [
        analyze_unresolved_gap(
            by_symbol[
                symbol
            ]
        )
        for symbol in policy[
            "required_unresolved_symbols"
        ]
    ]

    accession_review = (
        validate_accession_reuse(
            resolved_reviews
        )
    )

    review = build_review_ledger(
        sha256_bytes(
            ledger_path.read_bytes()
        ),
        resolved_reviews,
        accession_review,
        unresolved_reviews,
    )

    summary = write_outputs(
        review,
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
        if review[
            "reliability_review_passed"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
