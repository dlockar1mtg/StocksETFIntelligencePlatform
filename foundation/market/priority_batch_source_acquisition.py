from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class PriorityBatchSourceAcquisitionError(ValueError):
    """Raised when Phase 3.6b.3f fails closed."""


def _records(document: Any, key: str = "records") -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get(key), list):
        return document[key]
    raise PriorityBatchSourceAcquisitionError(f"{key.upper()}_ARRAY_MISSING")


def build_priority_batch_manifest(batch_plan: Any, policy: dict[str, Any]) -> dict[str, Any]:
    records = _records(batch_plan)
    batches = _records(batch_plan, "batches")
    required = int(policy["required_full_population"])
    if len(records) != required:
        raise PriorityBatchSourceAcquisitionError("FULL_POPULATION_COUNT_MISMATCH")
    identities = [record.get("security_id") for record in records]
    if None in identities or len(set(identities)) != required:
        raise PriorityBatchSourceAcquisitionError("DUPLICATE_OR_MISSING_SECURITY_ID")
    rank = int(policy["selected_priority_rank"])
    selected = [batch for batch in batches if int(batch.get("priority_rank", -1)) == rank]
    if len(selected) != 1:
        raise PriorityBatchSourceAcquisitionError("PRIORITY_BATCH_NOT_UNIQUE")
    batch = selected[0]
    if batch.get("issuer_key") != policy["selected_issuer_key"]:
        raise PriorityBatchSourceAcquisitionError("SELECTED_ISSUER_KEY_MISMATCH")
    if batch.get("issuer_name") != policy["selected_issuer_name"]:
        raise PriorityBatchSourceAcquisitionError("SELECTED_ISSUER_NAME_MISMATCH")
    security_ids = list(batch.get("security_ids") or [])
    if len(security_ids) != int(policy["selected_security_count"]):
        raise PriorityBatchSourceAcquisitionError("SELECTED_BATCH_COUNT_MISMATCH")
    by_id = {record["security_id"]: record for record in records}
    if any(security_id not in by_id for security_id in security_ids):
        raise PriorityBatchSourceAcquisitionError("BATCH_SECURITY_NOT_IN_PLAN")

    manifest_records: list[dict[str, Any]] = []
    for security_id in sorted(security_ids):
        source = by_id[security_id]
        if source.get("batch_state") != "BATCH_READY":
            raise PriorityBatchSourceAcquisitionError("NON_READY_SECURITY_IN_SELECTED_BATCH")
        manifest_records.append({
            "security_id": security_id,
            "symbol": source.get("symbol"),
            "issuer_key": batch["issuer_key"],
            "issuer_name": batch["issuer_name"],
            "priority_rank": rank,
            "acquisition_state": "PENDING",
            "allowed_source_tiers": list(policy["allowed_source_tiers"]),
            "selected_source_tier": None,
            "source_url": None,
            "retrieved_at_utc": None,
            "payload_sha256": None,
            "raw_path": None,
            "attempt_count": 0,
            "acquisition_reasons": ["SOURCE_ROUTE_NOT_YET_SELECTED"],
            "taxonomy_dimensions_assigned": False,
            "taxonomy_classification_authorized": False,
            "production_taxonomy_authority": False,
        })

    counts = Counter(record["acquisition_state"] for record in manifest_records)
    return {
        "phase": "3.6b.3f",
        "required_full_population": required,
        "selected_priority_rank": rank,
        "selected_issuer_key": batch["issuer_key"],
        "selected_issuer_name": batch["issuer_name"],
        "selected_security_count": len(manifest_records),
        "manifest_record_count": len(manifest_records),
        "acquisition_state_counts": dict(sorted(counts.items())),
        "manifest_complete": len(manifest_records) == int(policy["selected_security_count"]),
        "source_capture_executed": False,
        "next_required_step": "PRIORITY_BATCH_SOURCE_ROUTE_RESOLUTION",
        "execution": policy["execution"],
        "records": manifest_records,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {key: value for key, value in result.items() if key != "records"}
    compact["manifest_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
