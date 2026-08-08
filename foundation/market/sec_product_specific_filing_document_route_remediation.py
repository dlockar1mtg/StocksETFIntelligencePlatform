from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

FINAL_STATES = {
    "PRODUCT_SPECIFIC_DOCUMENT_RESOLVED",
    "DOCUMENT_CANDIDATE_UNRESOLVED",
    "DOCUMENT_IDENTITY_CONFLICTED",
    "DOCUMENT_QUARANTINED",
}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def review_ledger_contract_bytes(value: Any) -> bytes:
    """Reproduce the Phase 3.6b.3n governed review-ledger digest bytes.

    Phase 3.6b.3n hashes the logical pretty-printed JSON payload before Windows
    text-mode newline translation. Re-serializing the parsed object here avoids
    treating CRLF/LF storage differences as evidence drift.
    """
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def review_ledger_contract_sha256(value: Any) -> str:
    return sha256_bytes(review_ledger_contract_bytes(value))


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_inputs(review: dict[str, Any], capture: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    if review.get("phase") != policy["required_input_phase"]:
        raise ValueError("review phase mismatch")
    expected_review_hash = str(policy.get("required_review_ledger_sha256") or "")
    if expected_review_hash and review_ledger_contract_sha256(review) != expected_review_hash:
        raise ValueError("review ledger contract hash mismatch")
    records = list(review.get("records", []))
    if len(records) != int(policy["required_record_count"]):
        raise ValueError("review population mismatch")
    if sum(1 for r in records if r.get("review_state") == policy["required_failed_review_state"]) != int(policy["required_failed_record_count"]):
        raise ValueError("failed-state population mismatch")
    capture_records = list(capture.get("records", []))
    by_symbol = {str(r.get("symbol")): r for r in capture_records}
    pilot = []
    for symbol in policy["pilot_symbols"]:
        if symbol not in by_symbol:
            raise ValueError(f"missing pilot symbol: {symbol}")
        pilot.append(by_symbol[symbol])
    if len({r["security_id"] for r in pilot}) != len(pilot):
        raise ValueError("duplicate pilot identity")
    return pilot




def validate_corrected_pilot_manifest(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate the governed five-security corrected discovery manifest.

    This path is intentionally independent from the historical 347-record
    generic-capture review contract.
    """
    if (
        manifest.get("artifact_id")
        != "CORRECTED_SEC_ROUTE_DISCOVERY_PILOT_MANIFEST"
    ):
        raise ValueError(
            "corrected pilot manifest artifact mismatch"
        )

    if manifest.get("network_execution_authorized") is not False:
        raise ValueError(
            "pilot manifest itself may not authorize execution"
        )

    if int(manifest.get("pilot_record_count", 0)) != 5:
        raise ValueError(
            "corrected pilot record count mismatch"
        )

    if (
        int(
            manifest.get(
                "maximum_candidate_documents_per_security",
                0,
            )
        )
        != 5
    ):
        raise ValueError(
            "candidate-document ceiling mismatch"
        )

    if (
        int(
            manifest.get(
                "maximum_total_sec_requests",
                0,
            )
        )
        != 30
    ):
        raise ValueError(
            "total SEC request ceiling mismatch"
        )

    if (
        int(
            manifest.get(
                "maximum_requests_per_second",
                0,
            )
        )
        != 1
    ):
        raise ValueError(
            "SEC request-rate ceiling mismatch"
        )

    records = list(
        manifest.get("records", [])
    )

    if len(records) != 5:
        raise ValueError(
            "corrected pilot manifest must contain five records"
        )

    security_ids = [
        record.get("security_id")
        for record in records
    ]

    if (
        None in security_ids
        or len(set(security_ids)) != 5
    ):
        raise ValueError(
            "duplicate or missing corrected pilot security identity"
        )

    series_ids: list[str] = []
    class_ids: list[str] = []

    for record in records:
        for field in (
            "security_id",
            "symbol",
            "sec_cik",
            "sec_series_id",
            "sec_class_contract_id",
        ):
            if not record.get(field):
                raise ValueError(
                    f"missing corrected pilot field: {field}"
                )

        if (
            record.get("remediation_queue")
            != "FILING_ROUTE_DISCOVERY_REQUIRED"
        ):
            raise ValueError(
                "corrected pilot record is outside discovery queue"
            )

        if (
            int(
                record.get(
                    "maximum_candidate_documents",
                    0,
                )
            )
            != 5
        ):
            raise ValueError(
                "record candidate-document ceiling mismatch"
            )

        if (
            record.get(
                "prior_candidate_route_reuse_authorized"
            )
            is not False
        ):
            raise ValueError(
                "prior candidate-route reuse unexpectedly authorized"
            )

        if (
            record.get(
                "network_execution_authorized"
            )
            is not False
        ):
            raise ValueError(
                "record-level network execution unexpectedly authorized"
            )

        series_ids.append(
            str(record["sec_series_id"])
        )

        class_ids.append(
            str(
                record[
                    "sec_class_contract_id"
                ]
            )
        )

    if len(set(series_ids)) != 5:
        raise ValueError(
            "corrected pilot series identities are not unique"
        )

    if len(set(class_ids)) != 5:
        raise ValueError(
            "corrected pilot class identities are not unique"
        )

    return records

def iter_recent_filings(
    submissions: dict[str, Any],
    allowed_forms: Iterable[str],
    maximum: int,
) -> list[dict[str, str]]:
    """Return allowed issuer filings as candidates only.

    Recency and form type establish scan order. They do not establish
    product identity because one registrant can contain many ETF series.
    """
    recent = submissions.get(
        "filings",
        {},
    ).get(
        "recent",
        {},
    )

    forms = list(
        recent.get("form", [])
    )
    accessions = list(
        recent.get("accessionNumber", [])
    )
    primary_docs = list(
        recent.get("primaryDocument", [])
    )
    filing_dates = list(
        recent.get("filingDate", [])
    )

    allowed = set(allowed_forms)
    candidates: list[dict[str, str]] = []

    for index, form in enumerate(forms):
        if len(candidates) >= maximum:
            break

        if form not in allowed:
            continue

        if (
            index >= len(accessions)
            or index >= len(primary_docs)
        ):
            continue

        accession_number = str(
            accessions[index] or ""
        ).strip()

        primary_document = str(
            primary_docs[index] or ""
        ).strip()

        if (
            not accession_number
            or not primary_document
        ):
            continue

        candidates.append(
            {
                "form": str(form),
                "accession_number": accession_number,
                "primary_document": primary_document,
                "filing_date": (
                    str(
                        filing_dates[index]
                        or ""
                    )
                    if index < len(filing_dates)
                    else ""
                ),
            }
        )

    return candidates


def select_recent_filing(
    submissions: dict[str, Any],
    allowed_forms: Iterable[str],
    maximum: int,
) -> dict[str, str] | None:
    """Compatibility helper.

    This returns only the first candidate. Its return value must never be
    treated as product-specific evidence without document identity review.
    """
    candidates = iter_recent_filings(
        submissions,
        allowed_forms,
        maximum,
    )

    return candidates[0] if candidates else None



def _marker_present(
    value: Any,
    text: str,
) -> bool:
    """Prevent blank identifiers from matching every document."""
    normalized = str(
        value or ""
    ).strip().lower()

    return (
        bool(normalized)
        and normalized in text
    )


def _cik_marker_present(
    value: Any,
    text: str,
) -> bool:
    normalized = str(
        value or ""
    ).strip().lower()

    if not normalized:
        return False

    without_prefix = normalized.replace(
        "sec-cik-",
        "",
    )

    candidates = {
        normalized,
        without_prefix,
    }

    digits = without_prefix.lstrip("0")

    if digits:
        candidates.add(digits)

    return any(
        candidate
        and candidate in text
        for candidate in candidates
    )


def evaluate_document(
    record: dict[str, Any],
    payload: bytes,
    accession_number: str | None,
    primary_document: str | None,
) -> dict[str, Any]:
    text = payload.decode(
        "utf-8",
        errors="ignore",
    ).lower()

    markers = {
        "cik": _cik_marker_present(
            record.get("sec_cik"),
            text,
        ),
        "series_id": _marker_present(
            record.get("sec_series_id"),
            text,
        ),
        "class_contract_id": _marker_present(
            record.get("sec_class_contract_id"),
            text,
        ),
        "symbol": _marker_present(
            record.get("symbol"),
            text,
        ),
    }

    identity_count = sum(
        markers.values()
    )

    resolved = bool(
        accession_number
        and primary_document
        and markers["series_id"]
        and markers["class_contract_id"]
        and (
            markers["symbol"]
            or markers["cik"]
        )
    )

    state = (
        "PRODUCT_SPECIFIC_DOCUMENT_RESOLVED"
        if resolved
        else "DOCUMENT_CANDIDATE_UNRESOLVED"
    )

    return {
        "review_state": state,
        "identity_markers": markers,
        "identity_marker_count": identity_count,
        "product_specific": resolved,
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        state = record["review_state"]
        counts[state] = counts.get(state, 0) + 1
    resolved = counts.get("PRODUCT_SPECIFIC_DOCUMENT_RESOLVED", 0)
    complete = len(records) == 5 and all(r["review_state"] in FINAL_STATES for r in records)
    return {
        "phase": "3.6b.3o",
        "pilot_record_count": len(records),
        "pilot_complete": complete,
        "product_specific_document_count": resolved,
        "product_specific_document_rate": resolved / len(records) if records else 0.0,
        "review_state_counts": counts,
        "remediated_route_reliability_certification_authorized": False,
        "full_priority_batch_recapture_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": "REMEDIATED_ROUTE_PILOT_RELIABILITY_REVIEW_AND_CERTIFICATION",
    }


def write_outputs(ledger: dict[str, Any], output: str | Path, summary_path: str | Path) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(ledger)
    output_path.write_bytes(payload)
    summary = {k: v for k, v in ledger.items() if k != "records"}
    summary["remediation_ledger_sha256"] = sha256_bytes(payload)
    summary_file = Path(summary_path)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_bytes(canonical_json_bytes(summary))
