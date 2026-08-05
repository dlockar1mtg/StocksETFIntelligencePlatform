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


def select_recent_filing(submissions: dict[str, Any], allowed_forms: Iterable[str], maximum: int) -> dict[str, str] | None:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = list(recent.get("form", []))
    accessions = list(recent.get("accessionNumber", []))
    primary_docs = list(recent.get("primaryDocument", []))
    filing_dates = list(recent.get("filingDate", []))
    allowed = set(allowed_forms)
    for index, form in enumerate(forms[:maximum]):
        if form in allowed and index < len(accessions) and index < len(primary_docs):
            return {
                "form": form,
                "accession_number": accessions[index],
                "primary_document": primary_docs[index],
                "filing_date": filing_dates[index] if index < len(filing_dates) else "",
            }
    return None


def evaluate_document(record: dict[str, Any], payload: bytes, accession_number: str | None, primary_document: str | None) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="ignore").lower()
    markers = {
        "cik": str(record.get("sec_cik", "")).lstrip("0").lower() in text or str(record.get("sec_cik", "")).lower() in text,
        "series_id": str(record.get("sec_series_id", "")).lower() in text,
        "class_contract_id": str(record.get("sec_class_contract_id", "")).lower() in text,
        "symbol": str(record.get("symbol", "")).lower() in text,
    }
    identity_count = sum(markers.values())
    resolved = bool(accession_number and primary_document and markers["series_id"] and markers["class_contract_id"] and (markers["symbol"] or markers["cik"]))
    state = "PRODUCT_SPECIFIC_DOCUMENT_RESOLVED" if resolved else "DOCUMENT_CANDIDATE_UNRESOLVED"
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
