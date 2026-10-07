from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from foundation.market.sec_series_class_specific_filing_resolution import (
    build_summary,
    choose_resolution,
    document_names_from_index,
    evaluate_candidate,
    iter_candidate_filings,
    load_json,
    remediation_contract_sha256,
    sha256_bytes,
    validate_inputs,
    write_outputs,
)


def fetch(url: str, user_agent: str, timeout: int, retries: int) -> tuple[int | None, str, bytes, str | None]:
    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.geturl(), response.read(), None
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            last_error = f"HTTP_{exc.code}"
            if exc.code not in {429, 500, 502, 503, 504}:
                return exc.code, exc.geturl(), payload, last_error
        except Exception as exc:  # noqa: BLE001
            last_error = type(exc).__name__
        if attempt < retries:
            time.sleep(2**attempt)
    return None, url, b"", last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remediation-ledger", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()
    if "@" not in args.user_agent:
        raise ValueError("declared SEC user agent containing email is required")

    remediation = load_json(args.remediation_ledger)
    policy = load_json(args.policy)
    actual_hash = remediation_contract_sha256(remediation)
    if actual_hash != policy["required_remediation_ledger_sha256"]:
        raise ValueError("remediation ledger contract hash mismatch")
    pilot = validate_inputs(remediation, policy)
    route = policy["route"]
    execution = policy["execution"]
    root = Path(args.repository_root)
    request_cache: dict[str, tuple[int | None, str, bytes, str | None]] = {}

    maximum_total_sec_requests = int(
        execution[
            "maximum_total_sec_requests"
        ]
    )

    maximum_requests_per_second = int(
        execution[
            "maximum_requests_per_second"
        ]
    )

    maximum_retry_attempts = int(
        execution[
            "maximum_retry_attempts"
        ]
    )

    if maximum_total_sec_requests <= 0:
        raise ValueError(
            "maximum_total_sec_requests must be positive"
        )

    if maximum_requests_per_second <= 0:
        raise ValueError(
            "maximum_requests_per_second must be positive"
        )

    if maximum_retry_attempts != 0:
        raise ValueError(
            "series/class pilot retries must equal zero"
        )

    def governed_fetch(
        url: str,
    ) -> tuple[
        int | None,
        str,
        bytes,
        str | None,
    ]:
        if url not in request_cache:
            if (
                len(request_cache)
                >= maximum_total_sec_requests
            ):
                raise RuntimeError(
                    "absolute SEC request ceiling exhausted "
                    "before next physical request"
                )

            if request_cache:
                time.sleep(
                    1
                    / maximum_requests_per_second
                )

            request_cache[url] = fetch(
                url,
                args.user_agent,
                int(
                    execution[
                        "request_timeout_seconds"
                    ]
                ),
                maximum_retry_attempts,
            )

        return request_cache[url]

    records = []
    for sequence, source in enumerate(pilot, start=1):
        cik_digits = str(source["sec_cik"]).replace("SEC-CIK-", "").lstrip("0") or "0"
        cik10 = cik_digits.zfill(10)
        submissions_url = route["submissions_template"].format(cik10=cik10)
        submissions_status, _, submissions_payload, submissions_failure = governed_fetch(submissions_url)
        submissions_raw = Path(f"data/raw/sec_series_class_resolution/{args.operating_date}/{source['security_id']}/submissions.json")
        absolute = root / submissions_raw
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(submissions_payload)
        candidates: list[dict[str, object]] = []
        if submissions_status == 200:
            submissions = json.loads(submissions_payload.decode("utf-8"))
            filings = iter_candidate_filings(submissions, route["allowed_forms"], int(route["maximum_recent_filings_scanned"]))
            for filing in filings:
                accession_flat = filing["accession_number"].replace("-", "")
                index_url = route["archive_index_template"].format(cik_int=int(cik_digits), accession_no_dashes=accession_flat)
                index_status, _, index_payload, index_failure = governed_fetch(index_url)
                if index_status != 200:
                    continue
                try:
                    index_json = json.loads(index_payload.decode("utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                names = document_names_from_index(index_json, int(route["maximum_documents_per_filing"]))
                if filing.get("primary_document") and filing["primary_document"] not in names:
                    names.insert(0, filing["primary_document"])
                for document_name in names[: int(route["maximum_documents_per_filing"])]:
                    document_url = route["archive_document_template"].format(cik_int=int(cik_digits), accession_no_dashes=accession_flat, document_name=document_name)
                    status, final_url, payload, failure = governed_fetch(document_url)
                    if status != 200:
                        continue
                    evaluation = evaluate_candidate(source, payload)
                    raw_path = Path(f"data/raw/sec_series_class_resolution/{args.operating_date}/{source['security_id']}/{accession_flat}/{document_name}")
                    raw_absolute = root / raw_path
                    raw_absolute.parent.mkdir(parents=True, exist_ok=True)
                    raw_absolute.write_bytes(payload)
                    candidates.append({
                        **filing,
                        "document_name": document_name,
                        "document_url": document_url,
                        "document_final_url": final_url,
                        "document_http_status": status,
                        "document_failure": failure,
                        "document_payload_sha256": sha256_bytes(payload),
                        "document_raw_path": str(raw_path).replace("\\", "/"),
                        **evaluation,
                    })
                    if evaluation["product_specific"]:
                        break
                if any(c.get("product_specific") for c in candidates):
                    break
        resolution = choose_resolution(source, candidates)
        records.append({
            "sequence": sequence,
            "security_id": source["security_id"],
            "symbol": source["symbol"],
            "sec_cik": source["sec_cik"],
            "sec_series_id": source["sec_series_id"],
            "sec_class_contract_id": source["sec_class_contract_id"],
            "route_type": route["route_type"],
            "submissions_url": submissions_url,
            "submissions_http_status": submissions_status,
            "submissions_failure": submissions_failure,
            "submissions_payload_sha256": sha256_bytes(submissions_payload),
            "submissions_raw_path": str(submissions_raw).replace("\\", "/"),
            "candidate_document_count": len(candidates),
            "candidate_documents": candidates,
            **resolution,
            "taxonomy_dimensions_assigned": False,
            "taxonomy_classification_authorized": False,
            "production_taxonomy_authority": False,
        })

    summary = build_summary(records)
    ledger = {**summary, "route_type": route["route_type"], "request_count": len(request_cache), "records": records}
    output_summary = write_outputs(ledger, args.output, args.summary)
    print(json.dumps(output_summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
