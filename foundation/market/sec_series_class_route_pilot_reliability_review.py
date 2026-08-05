from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

RESOLVED_STATE = "SERIES_CLASS_DOCUMENT_RESOLVED"
UNRESOLVED_STATE = "SERIES_CLASS_DOCUMENT_UNRESOLVED"
ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def validate_resolution_contract(ledger_path: str | Path, ledger: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    actual_hash = sha256_bytes(Path(ledger_path).read_bytes())
    if actual_hash != policy["required_resolution_ledger_sha256"]:
        raise ValueError("resolution ledger SHA-256 mismatch")
    if ledger.get("phase") != policy["required_input_phase"]:
        raise ValueError("resolution phase mismatch")
    records = list(ledger.get("records", []))
    if len(records) != int(policy["required_pilot_record_count"]):
        raise ValueError("pilot record count mismatch")
    if [str(record.get("symbol")) for record in records] != list(policy["pilot_symbols"]):
        raise ValueError("pilot symbol order mismatch")
    by_symbol = {str(record.get("symbol")): record for record in records}
    if set(by_symbol) != set(policy["pilot_symbols"]):
        raise ValueError("pilot identity mismatch")
    for symbol in policy["required_resolved_symbols"]:
        if by_symbol[symbol].get("review_state") != RESOLVED_STATE:
            raise ValueError(f"required resolved record changed: {symbol}")
    for symbol in policy["required_unresolved_symbols"]:
        if by_symbol[symbol].get("review_state") != UNRESOLVED_STATE:
            raise ValueError(f"required unresolved record changed: {symbol}")
    return records


def marker_presence(record: dict[str, Any], payload: bytes) -> dict[str, bool]:
    text = payload.decode("utf-8", errors="ignore").lower()
    cik = str(record.get("sec_cik") or "").replace("SEC-CIK-", "").lstrip("0") or "0"
    return {
        "sec_cik": cik.lower() in text,
        "sec_series_id": str(record.get("sec_series_id") or "").lower() in text,
        "sec_class_contract_id": str(record.get("sec_class_contract_id") or "").lower() in text,
        "symbol": str(record.get("symbol") or "").lower() in text,
    }


def review_resolved_record(record: dict[str, Any], repository_root: str | Path, required_markers: list[str]) -> dict[str, Any]:
    raw_path_value = str(record.get("document_raw_path") or "")
    raw_path = Path(repository_root) / raw_path_value
    raw_present = bool(raw_path_value) and raw_path.is_file()
    payload = raw_path.read_bytes() if raw_present else b""
    stored_hash = str(record.get("document_payload_sha256") or "")
    computed_hash = sha256_bytes(payload) if raw_present else None
    markers = marker_presence(record, payload) if raw_present else {name: False for name in required_markers}
    accession = str(record.get("accession_number") or "")
    checks = {
        "raw_document_present": raw_present,
        "raw_document_hash_matches": raw_present and computed_hash == stored_hash,
        "accession_format_valid": bool(ACCESSION_PATTERN.fullmatch(accession)),
        "document_url_preserved": bool(record.get("document_url")),
        "document_final_url_preserved": bool(record.get("document_final_url")),
        "document_name_preserved": bool(record.get("document_name")),
        "filing_form_preserved": bool(record.get("form")),
        "filing_date_preserved": bool(record.get("filing_date")),
        "all_required_identity_markers_present": all(markers.get(name) is True for name in required_markers),
        "stored_identity_markers_agree": all(
            dict(record.get("identity_markers") or {}).get(name) is True for name in required_markers
        ),
    }
    reliable = all(checks.values())
    return {
        "security_id": record.get("security_id"),
        "symbol": record.get("symbol"),
        "review_state": "RESOLVED_DOCUMENT_RELIABLE" if reliable else "RESOLVED_DOCUMENT_RELIABILITY_FAILED",
        "accession_number": accession,
        "document_name": record.get("document_name"),
        "document_url": record.get("document_url"),
        "document_final_url": record.get("document_final_url"),
        "document_raw_path": raw_path_value,
        "stored_document_sha256": stored_hash,
        "recomputed_document_sha256": computed_hash,
        "identity_markers_recomputed": markers,
        "checks": checks,
        "reliable": reliable,
    }


def validate_accession_reuse(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for review in reviews:
        grouped.setdefault(str(review.get("accession_number") or ""), []).append(review)
    reused = {accession: values for accession, values in grouped.items() if accession and len(values) > 1}
    failures: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    for accession, values in reused.items():
        symbols = [str(value.get("symbol")) for value in values]
        independent_match = all(value.get("reliable") is True for value in values)
        item = {
            "accession_number": accession,
            "symbols": symbols,
            "independent_series_class_identity_confirmed": independent_match,
        }
        validations.append(item)
        if not independent_match:
            failures.append(item)
    return {
        "reused_accession_count": len(reused),
        "reused_accessions": validations,
        "incorrect_accession_reuse_detected": bool(failures),
        "accession_reuse_validation_passed": not failures,
    }


def analyze_aaxj_gap(record: dict[str, Any], candidate_floor: int) -> dict[str, Any]:
    candidates = list(record.get("candidate_documents", []))
    forms = sorted({str(item.get("form")) for item in candidates if item.get("form")})
    filing_dates = sorted(str(item.get("filing_date")) for item in candidates if item.get("filing_date"))
    any_series = any(dict(item.get("identity_markers") or {}).get("sec_series_id") is True for item in candidates)
    any_class = any(dict(item.get("identity_markers") or {}).get("sec_class_contract_id") is True for item in candidates)
    any_both = any(
        dict(item.get("identity_markers") or {}).get("sec_series_id") is True
        and dict(item.get("identity_markers") or {}).get("sec_class_contract_id") is True
        for item in candidates
    )
    floor_met = int(record.get("candidate_document_count", 0)) >= int(candidate_floor)
    return {
        "security_id": record.get("security_id"),
        "symbol": record.get("symbol"),
        "review_state": "TARGETED_HISTORICAL_REMEDIATION_REQUIRED",
        "candidate_document_count": record.get("candidate_document_count", 0),
        "candidate_floor_met": floor_met,
        "forms_examined": forms,
        "earliest_filing_date_examined": filing_dates[0] if filing_dates else None,
        "latest_filing_date_examined": filing_dates[-1] if filing_dates else None,
        "series_marker_seen_in_any_candidate": any_series,
        "class_marker_seen_in_any_candidate": any_class,
        "series_and_class_seen_together": any_both,
        "gap_findings": {
            "recent_submissions_window_did_not_resolve_identity": True,
            "older_sec_submission_history_files_required": True,
            "larger_filing_history_window_required": True,
            "additional_eligible_filing_forms_require_governed_review": True,
            "filing_header_or_complete_submission_text_inspection_required": True,
            "historical_accession_lookup_required": True,
            "alternate_sec_authoritative_route_required_now": False,
        },
        "next_remediation_scope": [
            "SEC_SUBMISSIONS_HISTORICAL_FILES",
            "EXPANDED_HISTORICAL_FILING_WINDOW",
            "GOVERNED_FORM_ELIGIBILITY_REVIEW",
            "FILING_HEADER_AND_COMPLETE_SUBMISSION_TEXT_INSPECTION",
            "HISTORICAL_ACCESSION_LOOKUP",
        ],
        "preserve_unresolved_state": True,
        "accession_assignment_authorized": False,
    }


def build_review_ledger(
    resolution_ledger_sha256: str,
    resolved_reviews: list[dict[str, Any]],
    accession_review: dict[str, Any],
    aaxj_gap: dict[str, Any],
) -> dict[str, Any]:
    all_resolved_reliable = bool(resolved_reviews) and all(item.get("reliable") is True for item in resolved_reviews)
    review_passed = all_resolved_reliable and accession_review["accession_reuse_validation_passed"] and aaxj_gap["candidate_floor_met"]
    return {
        "phase": "3.6b.3q",
        "required_input_phase": "3.6b.3p",
        "resolution_ledger_sha256": resolution_ledger_sha256,
        "reliability_review_complete": True,
        "reliability_review_passed": review_passed,
        "resolved_record_count_reviewed": len(resolved_reviews),
        "resolved_record_count_reliable": sum(item.get("reliable") is True for item in resolved_reviews),
        "all_resolved_records_independently_validated": all_resolved_reliable,
        "raw_document_hashes_recomputed": True,
        "accession_reuse_review": accession_review,
        "aaxj_gap_analysis": aaxj_gap,
        "series_class_route_reliability_certified": False,
        "full_priority_batch_recapture_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "benchmark_publication_authorized": False,
        "relative_return_analytics_authorized": False,
        "forecasting_authorized": False,
        "ranking_authorized": False,
        "recommendations_authorized": False,
        "portfolio_allocation_authorized": False,
        "uip_export_authorized": False,
        "next_required_step": "TARGETED_AAXJ_HISTORICAL_SEC_REMEDIATION",
        "resolved_records": resolved_reviews,
    }


def write_outputs(ledger: dict[str, Any], output_path: str | Path, summary_path: str | Path) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(ledger)
    output.write_bytes(payload)
    summary = {key: value for key, value in ledger.items() if key != "resolved_records"}
    summary["reliability_review_ledger_sha256"] = sha256_bytes(payload)
    target = Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_json_bytes(summary))
    return summary
