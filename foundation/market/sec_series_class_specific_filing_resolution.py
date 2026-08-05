from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

FINAL_STATES = {
    "SERIES_CLASS_DOCUMENT_RESOLVED",
    "SERIES_CLASS_DOCUMENT_UNRESOLVED",
    "SERIES_CLASS_DOCUMENT_CONFLICTED",
    "SERIES_CLASS_DOCUMENT_QUARANTINED",
}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def remediation_contract_sha256(value: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def validate_inputs(remediation: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    if remediation.get("phase") != policy["required_input_phase"]:
        raise ValueError("remediation phase mismatch")
    records = list(remediation.get("records", []))
    if len(records) != int(policy["required_pilot_record_count"]):
        raise ValueError("pilot population mismatch")
    if [str(r.get("symbol")) for r in records] != list(policy["pilot_symbols"]):
        raise ValueError("pilot symbol order mismatch")
    if any(r.get("review_state") != policy["required_input_review_state"] for r in records):
        raise ValueError("unexpected remediation review state")
    identities = [r.get("security_id") for r in records]
    if any(not value for value in identities) or len(set(identities)) != len(identities):
        raise ValueError("missing or duplicate security identity")
    return records


def iter_candidate_filings(submissions: dict[str, Any], allowed_forms: Iterable[str], maximum: int) -> list[dict[str, str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    fields = {
        "form": list(recent.get("form", [])),
        "accession_number": list(recent.get("accessionNumber", [])),
        "primary_document": list(recent.get("primaryDocument", [])),
        "filing_date": list(recent.get("filingDate", [])),
    }
    allowed = set(allowed_forms)
    candidates: list[dict[str, str]] = []
    for index, form in enumerate(fields["form"]):
        if len(candidates) >= maximum:
            break
        if form not in allowed:
            continue
        if index >= len(fields["accession_number"]):
            continue
        candidates.append({
            "form": form,
            "accession_number": fields["accession_number"][index],
            "primary_document": fields["primary_document"][index] if index < len(fields["primary_document"]) else "",
            "filing_date": fields["filing_date"][index] if index < len(fields["filing_date"]) else "",
        })
    return candidates


def document_names_from_index(index_json: dict[str, Any], maximum: int) -> list[str]:
    items = index_json.get("directory", {}).get("item", [])
    names: list[str] = []
    for item in items:
        name = str(item.get("name") or "")
        lower = name.lower()
        if not name or lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".xml")):
            continue
        if lower.endswith((".htm", ".html", ".txt")) and name not in names:
            names.append(name)
        if len(names) >= maximum:
            break
    return names


def evaluate_candidate(record: dict[str, Any], payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="ignore").lower()
    markers = {
        "sec_series_id": str(record.get("sec_series_id") or "").lower() in text,
        "sec_class_contract_id": str(record.get("sec_class_contract_id") or "").lower() in text,
        "symbol": str(record.get("symbol") or "").lower() in text,
        "sec_cik": str(record.get("sec_cik") or "").lstrip("0").lower() in text,
    }
    required = markers["sec_series_id"] and markers["sec_class_contract_id"]
    supporting = markers["symbol"] or markers["sec_cik"]
    return {
        "identity_markers": markers,
        "identity_marker_count": sum(markers.values()),
        "product_specific": bool(required and supporting),
    }


def choose_resolution(record: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [candidate for candidate in candidates if candidate.get("product_specific") is True]
    if len(matches) == 1:
        chosen = dict(matches[0])
        chosen["review_state"] = "SERIES_CLASS_DOCUMENT_RESOLVED"
        return chosen
    if len(matches) > 1:
        return {
            "review_state": "SERIES_CLASS_DOCUMENT_CONFLICTED",
            "matching_candidate_count": len(matches),
            "matching_candidates": matches,
            "product_specific": False,
        }
    return {
        "review_state": "SERIES_CLASS_DOCUMENT_UNRESOLVED",
        "matching_candidate_count": 0,
        "matching_candidates": [],
        "product_specific": False,
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        state = record["review_state"]
        counts[state] = counts.get(state, 0) + 1
    resolved = counts.get("SERIES_CLASS_DOCUMENT_RESOLVED", 0)
    return {
        "phase": "3.6b.3p",
        "pilot_record_count": len(records),
        "pilot_complete": len(records) == 5 and all(r["review_state"] in FINAL_STATES for r in records),
        "resolved_record_count": resolved,
        "resolved_rate": resolved / len(records) if records else 0.0,
        "review_state_counts": counts,
        "series_class_route_reliability_certification_authorized": False,
        "full_priority_batch_recapture_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": "SERIES_CLASS_ROUTE_PILOT_RELIABILITY_REVIEW_AND_CERTIFICATION",
    }


def write_outputs(ledger: dict[str, Any], output_path: str | Path, summary_path: str | Path) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(ledger)
    output.write_bytes(payload)
    summary = {k: v for k, v in ledger.items() if k != "records"}
    summary["resolution_ledger_sha256"] = sha256_bytes(payload)
    target = Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_json_bytes(summary))
    return summary
