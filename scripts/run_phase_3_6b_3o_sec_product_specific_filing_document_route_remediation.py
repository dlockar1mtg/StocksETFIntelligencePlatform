from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from foundation.market.sec_product_specific_filing_document_route_remediation import (
    build_summary,
    evaluate_document,
    load_json,
    iter_recent_filings,
    sha256_bytes,
    validate_inputs,
    validate_corrected_pilot_manifest,
    write_outputs,
)


def fetch(url: str, user_agent: str, timeout: int, retries: int) -> tuple[int | None, str, bytes, list[str], str | None]:
    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.geturl(), response.read(), [url, response.geturl()], None
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            last_error = f"HTTP_{exc.code}"
            if exc.code not in {429, 500, 502, 503, 504}:
                return exc.code, exc.geturl(), payload, [url, exc.geturl()], last_error
        except Exception as exc:  # noqa: BLE001
            last_error = type(exc).__name__
        if attempt < retries:
            time.sleep(2**attempt)
    return None, url, b"", [url], last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-ledger")
    parser.add_argument("--review-ledger")
    parser.add_argument("--pilot-manifest")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()

    if "@" not in args.user_agent:
        raise ValueError("declared SEC user agent containing email is required")

    policy = load_json(args.policy)

    using_manifest = bool(
        args.pilot_manifest
    )

    using_legacy = bool(
        args.capture_ledger
        or args.review_ledger
    )

    if using_manifest and using_legacy:
        raise ValueError(
            "pilot manifest and legacy ledgers are mutually exclusive"
        )

    if using_manifest:
        manifest = load_json(
            args.pilot_manifest
        )

        pilot = (
            validate_corrected_pilot_manifest(
                manifest
            )
        )
    else:
        if (
            not args.capture_ledger
            or not args.review_ledger
        ):
            raise ValueError(
                "either --pilot-manifest or both legacy ledgers are required"
            )

        capture = load_json(
            args.capture_ledger
        )

        review = load_json(
            args.review_ledger
        )

        pilot = validate_inputs(
            review,
            capture,
            policy,
        )
    route = policy["route"]
    execution = policy["execution"]

    corrected_pilot_mode = bool(
        args.pilot_manifest
    )

    effective_retry_attempts = (
        0
        if corrected_pilot_mode
        else int(
            execution[
                "maximum_retry_attempts"
            ]
        )
    )

    request_interval_seconds = (
        1
        / int(
            execution[
                "maximum_requests_per_second"
            ]
        )
    )

    root = Path(args.repository_root)
    records = []

    for sequence, source in enumerate(pilot, start=1):
        cik_digits = str(source["sec_cik"]).replace("SEC-CIK-", "").lstrip("0") or "0"
        cik10 = cik_digits.zfill(10)
        submissions_url = route["submissions_template"].format(cik10=cik10)
        if corrected_pilot_mode:
            time.sleep(
                request_interval_seconds
            )

        status, final_url, submissions_payload, redirects, failure = fetch(
            submissions_url,
            args.user_agent,
            int(execution["request_timeout_seconds"]),
            effective_retry_attempts,
        )
        submissions_raw = Path(f"data/raw/sec_filing_route_remediation/{args.operating_date}/{source['security_id']}/submissions.json")
        absolute_submissions = root / submissions_raw
        absolute_submissions.parent.mkdir(parents=True, exist_ok=True)
        absolute_submissions.write_bytes(submissions_payload)


        filing_candidates = []

        if status == 200:
            try:
                filing_candidates = iter_recent_filings(
                    json.loads(
                        submissions_payload.decode(
                            "utf-8"
                        )
                    ),
                    route["allowed_forms"],
                    min(
                        int(
                            route[
                                "maximum_recent_filings_scanned"
                            ]
                        ),
                        int(
                            route[
                                "maximum_candidate_documents_per_security"
                            ]
                        ),
                    ),
                )
            except Exception:  # noqa: BLE001
                failure = "SUBMISSIONS_PARSE_FAILED"

        filing = None
        document_payload = b""
        document_status = None
        document_url = None
        document_final_url = None
        document_redirects: list[str] = []
        document_failure = None
        document_raw = None

        candidate_attempts = []

        evaluation = evaluate_document(
            source,
            b"",
            None,
            None,
        )

        for candidate in filing_candidates:
            accession_no = candidate[
                "accession_number"
            ]

            accession_flat = (
                accession_no.replace(
                    "-",
                    "",
                )
            )

            candidate_url = route[
                "archive_document_template"
            ].format(
                cik_int=int(cik_digits),
                accession_no_dashes=(
                    accession_flat
                ),
                primary_document=candidate[
                    "primary_document"
                ],
            )

            time.sleep(
                request_interval_seconds
            )

            (
                candidate_status,
                candidate_final_url,
                candidate_payload,
                candidate_redirects,
                candidate_failure,
            ) = fetch(
                candidate_url,
                args.user_agent,
                int(
                    execution[
                        "request_timeout_seconds"
                    ]
                ),
                effective_retry_attempts,
            )

            candidate_raw = Path(
                "data/raw/"
                "sec_filing_route_remediation/"
                f"{args.operating_date}/"
                f"{source['security_id']}/"
                f"{accession_flat}/"
                f"{candidate['primary_document']}"
            )

            absolute_document = (
                root / candidate_raw
            )

            absolute_document.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            absolute_document.write_bytes(
                candidate_payload
            )

            candidate_evaluation = (
                evaluate_document(
                    source,
                    candidate_payload,
                    candidate[
                        "accession_number"
                    ],
                    candidate[
                        "primary_document"
                    ],
                )
            )

            if candidate_status != 200:
                candidate_evaluation[
                    "review_state"
                ] = "DOCUMENT_QUARANTINED"

            candidate_attempts.append(
                {
                    "form": candidate["form"],
                    "filing_date": candidate[
                        "filing_date"
                    ],
                    "accession_number": candidate[
                        "accession_number"
                    ],
                    "primary_document": candidate[
                        "primary_document"
                    ],
                    "document_url": (
                        candidate_url
                    ),
                    "document_http_status": (
                        candidate_status
                    ),
                    "document_final_url": (
                        candidate_final_url
                    ),
                    "document_redirect_chain": (
                        candidate_redirects
                    ),
                    "document_failure": (
                        candidate_failure
                    ),
                    "document_payload_sha256": (
                        sha256_bytes(
                            candidate_payload
                        )
                    ),
                    "document_raw_path": str(
                        candidate_raw
                    ).replace(
                        "\\",
                        "/",
                    ),
                    **candidate_evaluation,
                }
            )

            if (
                candidate_status == 200
                and candidate_evaluation[
                    "product_specific"
                ]
                is True
            ):
                filing = candidate
                document_payload = (
                    candidate_payload
                )
                document_status = (
                    candidate_status
                )
                document_url = candidate_url
                document_final_url = (
                    candidate_final_url
                )
                document_redirects = (
                    candidate_redirects
                )
                document_failure = (
                    candidate_failure
                )
                document_raw = (
                    candidate_raw
                )
                evaluation = (
                    candidate_evaluation
                )
                break

        if filing is None:
            evaluation = evaluate_document(
                source,
                b"",
                None,
                None,
            )

            evaluation[
                "review_state"
            ] = "DOCUMENT_CANDIDATE_UNRESOLVED"


        records.append({
            "sequence": sequence,
            "security_id": source["security_id"],
            "symbol": source["symbol"],
            "sec_cik": source["sec_cik"],
            "sec_series_id": source["sec_series_id"],
            "sec_class_contract_id": source["sec_class_contract_id"],
            "route_type": route["route_type"],
            "submissions_url": submissions_url,
            "submissions_http_status": status,
            "submissions_final_url": final_url,
            "submissions_redirect_chain": redirects,
            "submissions_payload_sha256": sha256_bytes(submissions_payload),
            "submissions_raw_path": str(submissions_raw).replace("\\", "/"),
            "submissions_failure": failure,
            "form": filing["form"] if filing else None,
            "filing_date": filing["filing_date"] if filing else None,
            "accession_number": filing["accession_number"] if filing else None,
            "primary_document": filing["primary_document"] if filing else None,
            "document_url": document_url,
            "document_http_status": document_status,
            "document_final_url": document_final_url,
            "document_redirect_chain": document_redirects,
            "document_payload_sha256": sha256_bytes(document_payload),
            "document_raw_path": str(document_raw).replace("\\", "/") if document_raw else None,
            "document_failure": document_failure,
            "candidate_document_attempts": candidate_attempts,
            "candidate_document_attempt_count": len(candidate_attempts),
            **evaluation,
            "taxonomy_dimensions_assigned": False,
            "taxonomy_classification_authorized": False,
            "production_taxonomy_authority": False,
        })
        time.sleep(1 / int(execution["maximum_requests_per_second"]))

    summary = build_summary(records)
    ledger = {**summary, "route_type": route["route_type"], "records": records}
    write_outputs(ledger, args.output, args.summary)
    print(json.dumps({k: v for k, v in ledger.items() if k != "records"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
