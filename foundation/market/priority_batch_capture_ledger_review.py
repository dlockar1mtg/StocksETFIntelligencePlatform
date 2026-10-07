from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

FINAL_CAPTURE_STATES = {
    "CAPTURED",
    "CAPTURE_UNRESOLVED",
    "CAPTURE_CONFLICTED",
    "CAPTURE_QUARANTINED",
}


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _contains(payload_text: str, marker: Any) -> bool:
    text = str(marker or "").strip()
    return bool(text) and text.lower() in payload_text.lower()


def validate_inputs(ledger: dict[str, Any], policy: dict[str, Any]) -> None:
    records = ledger.get("records")
    if ledger.get("phase") != policy["required_input_phase"]:
        raise ValueError("Unexpected capture-ledger phase")
    if not isinstance(records, list) or len(records) != policy["required_record_count"]:
        raise ValueError("Capture-ledger population drift")
    if ledger.get("capture_ledger_complete") is not True:
        raise ValueError("Capture ledger is incomplete")
    if ledger.get("final_record_count") != policy["required_record_count"]:
        raise ValueError("Final-record count drift")
    identities = [record.get("security_id") for record in records]
    if any(not value for value in identities) or len(set(identities)) != len(identities):
        raise ValueError("Missing or duplicate security identity")
    for record in records:
        if record.get("capture_state") not in FINAL_CAPTURE_STATES:
            raise ValueError(f"Nonfinal capture state: {record.get('security_id')}")
        if record.get("route_type") != policy["required_route_type"]:
            raise ValueError(f"Unexpected route: {record.get('security_id')}")


def review_capture_ledger(
    ledger: dict[str, Any],
    policy: dict[str, Any],
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    validate_inputs(ledger, policy)
    root = Path(repository_root)
    records = ledger["records"]

    hash_groups: dict[str, list[str]] = defaultdict(list)
    raw_cache: dict[str, tuple[bytes | None, str | None]] = {}

    for record in records:
        raw_path = str(record.get("raw_path") or "")
        resolved = Path(raw_path)
        if not resolved.is_absolute():
            resolved = root / resolved
        if not resolved.exists() or not resolved.is_file():
            raw_cache[record["security_id"]] = (None, None)
            continue
        payload = resolved.read_bytes()
        actual_hash = _sha256_bytes(payload)
        raw_cache[record["security_id"]] = (payload, actual_hash)
        hash_groups[actual_hash].append(record["security_id"])

    reviewed_records: list[dict[str, Any]] = []
    for record in records:
        security_id = record["security_id"]
        payload, actual_hash = raw_cache[security_id]
        expected_hash = record.get("payload_sha256")
        group_size = len(hash_groups.get(actual_hash or "", [])) if actual_hash else 0
        marker_results = {
            "sec_cik": False,
            "sec_series_id": False,
            "sec_class_contract_id": False,
            "symbol": False,
        }
        reasons: list[str] = []

        if payload is None:
            review_state = "RAW_EVIDENCE_MISSING"
            reasons.append("RAW_EVIDENCE_MISSING")
        elif actual_hash != expected_hash:
            review_state = "RAW_HASH_MISMATCH"
            reasons.append("RAW_HASH_MISMATCH")
        else:
            text = payload.decode("utf-8", errors="replace")
            marker_results = {
                "sec_cik": _contains(text, record.get("sec_cik")),
                "sec_series_id": _contains(text, record.get("sec_series_id")),
                "sec_class_contract_id": _contains(text, record.get("sec_class_contract_id")),
                "symbol": _contains(text, record.get("symbol")),
            }
            marker_complete = all(marker_results.values())
            if group_size > policy["thresholds"]["maximum_shared_payload_group_size_for_product_specific"]:
                review_state = "GENERIC_SHARED_PAYLOAD"
                reasons.append("PAYLOAD_SHARED_ACROSS_MULTIPLE_SECURITIES")
            elif not marker_complete:
                review_state = "IDENTITY_MARKER_INCOMPLETE"
                reasons.extend(
                    f"MISSING_{name.upper()}" for name, present in marker_results.items() if not present
                )
            else:
                review_state = "PRODUCT_SPECIFIC_EVIDENCE"
                reasons.append("ALL_EXPECTED_MARKERS_PRESENT")

        reviewed_records.append(
            {
                "sequence": record.get("sequence"),
                "security_id": security_id,
                "symbol": record.get("symbol"),
                "capture_state": record.get("capture_state"),
                "review_state": review_state,
                "payload_sha256": expected_hash,
                "recomputed_payload_sha256": actual_hash,
                "shared_payload_group_size": group_size,
                "identity_marker_results": marker_results,
                "review_reasons": reasons,
                "raw_path": record.get("raw_path"),
                "taxonomy_dimensions_assigned": False,
                "taxonomy_classification_authorized": False,
                "production_taxonomy_authority": False,
            }
        )

    state_counts = Counter(item["review_state"] for item in reviewed_records)
    product_specific_count = state_counts.get("PRODUCT_SPECIFIC_EVIDENCE", 0)
    record_count = len(reviewed_records)
    raw_hash_valid_count = sum(
        1
        for item in reviewed_records
        if item["recomputed_payload_sha256"]
        and item["recomputed_payload_sha256"] == item["payload_sha256"]
    )
    marker_complete_count = sum(
        1 for item in reviewed_records if all(item["identity_marker_results"].values())
    )
    unique_payload_count = len(hash_groups)
    largest_shared_group_size = max((len(values) for values in hash_groups.values()), default=0)

    product_specific_rate = product_specific_count / record_count if record_count else 0.0
    raw_hash_coverage = raw_hash_valid_count / record_count if record_count else 0.0
    marker_coverage = marker_complete_count / record_count if record_count else 0.0

    certification_eligible = (
        product_specific_rate >= policy["thresholds"]["minimum_product_specific_rate_for_certification"]
        and raw_hash_coverage >= policy["thresholds"]["required_raw_hash_coverage"]
        and marker_coverage >= policy["thresholds"]["required_identity_marker_coverage"]
        and largest_shared_group_size
        <= policy["thresholds"]["maximum_shared_payload_group_size_for_product_specific"]
    )

    next_step = (
        "PRIORITY_BATCH_TAXONOMY_EVIDENCE_NORMALIZATION_AUTHORIZATION"
        if certification_eligible
        else "SEC_PRODUCT_SPECIFIC_FILING_DOCUMENT_ROUTE_REMEDIATION"
    )

    shared_groups = [
        {
            "payload_sha256": payload_hash,
            "record_count": len(security_ids),
            "security_ids": sorted(security_ids),
        }
        for payload_hash, security_ids in sorted(hash_groups.items())
        if len(security_ids) > 1
    ]

    return {
        "phase": "3.6b.3n",
        "input_phase": ledger["phase"],
        "record_count": record_count,
        "review_complete": True,
        "unique_payload_count": unique_payload_count,
        "largest_shared_payload_group_size": largest_shared_group_size,
        "product_specific_evidence_count": product_specific_count,
        "product_specific_evidence_rate": product_specific_rate,
        "raw_hash_coverage_rate": raw_hash_coverage,
        "identity_marker_coverage_rate": marker_coverage,
        "review_state_counts": dict(sorted(state_counts.items())),
        "shared_payload_groups": shared_groups,
        "capture_ledger_certification_authorized": certification_eligible,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": next_step,
        "records": reviewed_records,
    }


def write_review(
    review: dict[str, Any], output_path: str | Path, summary_path: str | Path
) -> dict[str, Any]:
    output = Path(output_path)
    summary = Path(summary_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(review, indent=2, sort_keys=True) + "\n"
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    summary_value = {
        "phase": review["phase"],
        "record_count": review["record_count"],
        "unique_payload_count": review["unique_payload_count"],
        "largest_shared_payload_group_size": review["largest_shared_payload_group_size"],
        "product_specific_evidence_count": review["product_specific_evidence_count"],
        "capture_ledger_certification_authorized": review[
            "capture_ledger_certification_authorized"
        ],
        "next_required_step": review["next_required_step"],
        "review_ledger_sha256": digest,
    }
    summary.write_text(json.dumps(summary_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_value


def load_and_review(
    ledger_path: str | Path,
    policy_path: str | Path,
    output_path: str | Path,
    summary_path: str | Path,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    ledger = _load_json(ledger_path)
    policy = _load_json(policy_path)
    review = review_capture_ledger(ledger, policy, repository_root=repository_root)
    return write_review(review, output_path, summary_path)
