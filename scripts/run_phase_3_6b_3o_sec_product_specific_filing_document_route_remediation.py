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
    select_recent_filing,
    sha256_bytes,
    validate_inputs,
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
    parser.add_argument("--capture-ledger", required=True)
    parser.add_argument("--review-ledger", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()

    if "@" not in args.user_agent:
        raise ValueError("declared SEC user agent containing email is required")

    capture = load_json(args.capture_ledger)
    review = load_json(args.review_ledger)
    policy = load_json(args.policy)
    pilot = validate_inputs(review, capture, policy)
    route = policy["route"]
    execution = policy["execution"]
    root = Path(args.repository_root)
    records = []

    for sequence, source in enumerate(pilot, start=1):
        cik_digits = str(source["sec_cik"]).replace("SEC-CIK-", "").lstrip("0") or "0"
        cik10 = cik_digits.zfill(10)
        submissions_url = route["submissions_template"].format(cik10=cik10)
        status, final_url, submissions_payload, redirects, failure = fetch(
            submissions_url,
            args.user_agent,
            int(execution["request_timeout_seconds"]),
            int(execution["maximum_retry_attempts"]),
        )
        submissions_raw = Path(f"data/raw/sec_filing_route_remediation/{args.operating_date}/{source['security_id']}/submissions.json")
        absolute_submissions = root / submissions_raw
        absolute_submissions.parent.mkdir(parents=True, exist_ok=True)
        absolute_submissions.write_bytes(submissions_payload)

        filing = None
        if status == 200:
            try:
                filing = select_recent_filing(
                    json.loads(submissions_payload.decode("utf-8")),
                    route["allowed_forms"],
                    int(route["maximum_recent_filings_scanned"]),
                )
            except Exception:  # noqa: BLE001
                failure = "SUBMISSIONS_PARSE_FAILED"

        document_payload = b""
        document_status = None
        document_url = None
        document_final_url = None
        document_redirects: list[str] = []
        document_failure = None
        document_raw = None
        if filing:
            accession_no = filing["accession_number"]
            accession_flat = accession_no.replace("-", "")
            document_url = route["archive_document_template"].format(
                cik_int=int(cik_digits),
                accession_no_dashes=accession_flat,
                primary_document=filing["primary_document"],
            )
            time.sleep(1 / int(execution["maximum_requests_per_second"]))
            document_status, document_final_url, document_payload, document_redirects, document_failure = fetch(
                document_url,
                args.user_agent,
                int(execution["request_timeout_seconds"]),
                int(execution["maximum_retry_attempts"]),
            )
            document_raw = Path(f"data/raw/sec_filing_route_remediation/{args.operating_date}/{source['security_id']}/{accession_flat}/{filing['primary_document']}")
            absolute_document = root / document_raw
            absolute_document.parent.mkdir(parents=True, exist_ok=True)
            absolute_document.write_bytes(document_payload)

        evaluation = evaluate_document(
            source,
            document_payload,
            filing["accession_number"] if filing else None,
            filing["primary_document"] if filing else None,
        )
        if not filing:
            evaluation["review_state"] = "DOCUMENT_CANDIDATE_UNRESOLVED"
        if document_status not in {None, 200}:
            evaluation["review_state"] = "DOCUMENT_QUARANTINED"

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
