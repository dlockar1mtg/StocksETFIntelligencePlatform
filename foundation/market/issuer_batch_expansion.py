from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class IssuerBatchExpansionError(ValueError):
    """Raised when Phase 3.6b.3c batch planning fails closed."""


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise IssuerBatchExpansionError("RECORD_ARRAY_MISSING")


def _pilot_ids(pilot_taxonomy: Any) -> set[str]:
    records = _records(pilot_taxonomy)
    classified = {
        str(record.get("security_id"))
        for record in records
        if record.get("classification_status") == "CLASSIFIED"
        and record.get("taxonomy_classification_authorized") is True
    }
    if len(classified) != 3:
        raise IssuerBatchExpansionError("PILOT_CLASSIFICATION_INCOMPLETE")
    return classified


def build_issuer_batch_plan(
    acquisition_manifest: Any,
    pilot_taxonomy: Any,
    policy: dict[str, Any],
) -> dict[str, Any]:
    records = _records(acquisition_manifest)
    required = int(policy["required_full_population"])
    if len(records) != required:
        raise IssuerBatchExpansionError("FULL_POPULATION_COUNT_MISMATCH")

    identities = [record.get("security_id") for record in records]
    if None in identities or len(set(identities)) != required:
        raise IssuerBatchExpansionError("DUPLICATE_OR_MISSING_SECURITY_ID")

    pilot_ids = _pilot_ids(pilot_taxonomy)
    manifest_ids = set(str(value) for value in identities)
    if not pilot_ids.issubset(manifest_ids):
        raise IssuerBatchExpansionError("PILOT_IDENTITY_NOT_IN_MANIFEST")

    issuer_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    planned_records: list[dict[str, Any]] = []

    for source in records:
        security_id = str(source["security_id"])
        symbol = source.get("symbol")
        issuer_key = source.get("issuer_key")
        reasons: list[str] = []

        if security_id in pilot_ids:
            state = "PILOT_COMPLETE"
            reasons.append("PILOT_TAXONOMY_CLASSIFIED")
        elif source.get("acquisition_state") in {"CONFLICTED", "QUARANTINED"}:
            state = str(source.get("acquisition_state"))
            reasons.append("ACQUISITION_STATE_BLOCKS_BATCHING")
        elif not issuer_key:
            state = "ISSUER_EVIDENCE_REQUIRED"
            reasons.append("EVIDENCE_BACKED_ISSUER_KEY_MISSING")
        else:
            state = "BATCH_READY"
            reasons.append("EVIDENCE_BACKED_ISSUER_KEY_PRESENT")
            issuer_groups[str(issuer_key)].append(source)

        planned_records.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "issuer_key": issuer_key,
                "batch_state": state,
                "batch_reasons": reasons,
                "taxonomy_dimensions_assigned": False,
                "production_taxonomy_authority": False,
            }
        )

    batches: list[dict[str, Any]] = []
    for issuer_key, members in issuer_groups.items():
        member_ids = sorted(str(member["security_id"]) for member in members)
        batches.append(
            {
                "issuer_key": issuer_key,
                "etf_count": len(member_ids),
                "security_ids": member_ids,
                "batch_state": "BATCH_READY",
                "source_capture_authorized": False,
            }
        )

    batches.sort(key=lambda item: (-int(item["etf_count"]), str(item["issuer_key"])))
    for index, batch in enumerate(batches, start=1):
        batch["priority_rank"] = index

    state_counts = Counter(record["batch_state"] for record in planned_records)
    batch_ready_count = state_counts.get("BATCH_READY", 0)
    issuer_evidence_required = state_counts.get("ISSUER_EVIDENCE_REQUIRED", 0)

    if batch_ready_count > 0:
        next_step = "AUTHORITATIVE_SOURCE_CAPTURE_BY_PRIORITY_BATCH"
    elif issuer_evidence_required > 0:
        next_step = "EVIDENCE_BACKED_ISSUER_IDENTITY_ACQUISITION"
    else:
        next_step = "BATCH_EXCEPTION_REVIEW"

    return {
        "phase": "3.6b.3c",
        "required_full_population": required,
        "record_count": len(planned_records),
        "completed_pilot_count": len(pilot_ids),
        "remaining_population": required - len(pilot_ids),
        "batch_state_counts": dict(sorted(state_counts.items())),
        "issuer_batch_count": len(batches),
        "batch_ready_security_count": batch_ready_count,
        "issuer_evidence_required_count": issuer_evidence_required,
        "batch_plan_complete": issuer_evidence_required == 0,
        "next_required_step": next_step,
        "batches": batches,
        "records": planned_records,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_payload = {key: value for key, value in result.items() if key not in {"records", "batches"}}
    summary_payload["top_batches"] = result["batches"][:20]
    summary_payload["batch_plan_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
