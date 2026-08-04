from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class IssuerBatchPlanRebuildError(ValueError):
    pass


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise IssuerBatchPlanRebuildError("RECORD_ARRAY_MISSING")


def build_issuer_batch_plan(ledger_document: Any, policy: dict[str, Any]) -> dict[str, Any]:
    ledger = _records(ledger_document)
    required = int(policy["required_full_population"])
    if len(ledger) != required:
        raise IssuerBatchPlanRebuildError("FULL_POPULATION_COUNT_MISMATCH")
    security_ids = [record.get("security_id") for record in ledger]
    if None in security_ids or len(set(security_ids)) != required:
        raise IssuerBatchPlanRebuildError("DUPLICATE_OR_MISSING_SECURITY_ID")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    planned: list[dict[str, Any]] = []
    pilot_count = 0

    for source in ledger:
        state = str(source.get("issuer_identity_state"))
        security_id = str(source["security_id"])
        issuer_key = source.get("issuer_key")
        reasons: list[str] = []

        if state == "PILOT_COMPLETE":
            batch_state = "PILOT_COMPLETE"
            pilot_count += 1
            reasons.append("PILOT_TAXONOMY_ALREADY_COMPLETE")
        elif state == "ISSUER_CONFIRMED" and issuer_key:
            batch_state = "BATCH_READY"
            reasons.append("CONFIRMED_ISSUER_IDENTITY_AVAILABLE")
            groups[str(issuer_key)].append(source)
        elif state in {"ISSUER_CONFLICTED", "ISSUER_QUARANTINED", "ISSUER_UNRESOLVED"}:
            batch_state = state
            reasons.append("ISSUER_IDENTITY_STATE_BLOCKS_BATCHING")
        else:
            batch_state = "ISSUER_UNRESOLVED"
            reasons.append("ISSUER_IDENTITY_CONTRACT_NOT_SATISFIED")

        planned.append({
            "security_id": security_id,
            "symbol": source.get("symbol"),
            "issuer_key": issuer_key,
            "issuer_name": source.get("issuer_name"),
            "issuer_entity_role": source.get("issuer_entity_role"),
            "batch_state": batch_state,
            "batch_reasons": reasons,
            "taxonomy_dimensions_assigned": False,
            "source_capture_authorized": False,
            "production_taxonomy_authority": False,
        })

    if pilot_count != int(policy["completed_pilot_count"]):
        raise IssuerBatchPlanRebuildError("PILOT_COUNT_MISMATCH")

    batches: list[dict[str, Any]] = []
    for issuer_key, members in groups.items():
        ordered = sorted(members, key=lambda item: (str(item.get("symbol") or ""), str(item["security_id"])))
        batches.append({
            "issuer_key": issuer_key,
            "issuer_name": ordered[0].get("issuer_name"),
            "issuer_entity_role": ordered[0].get("issuer_entity_role"),
            "security_count": len(ordered),
            "security_ids": [str(item["security_id"]) for item in ordered],
            "symbols": [item.get("symbol") for item in ordered],
            "batch_state": "BATCH_READY",
            "source_capture_authorized": False,
            "taxonomy_classification_authorized": False,
        })

    batches.sort(key=lambda item: (-int(item["security_count"]), str(item["issuer_key"])))
    cumulative = 0
    ready_total = sum(int(batch["security_count"]) for batch in batches)
    for rank, batch in enumerate(batches, start=1):
        cumulative += int(batch["security_count"])
        batch["priority_rank"] = rank
        batch["cumulative_security_count"] = cumulative
        batch["cumulative_ready_coverage"] = cumulative / ready_total if ready_total else 0.0
        batch["full_population_coverage"] = cumulative / required

    counts = Counter(record["batch_state"] for record in planned)
    blocked = sum(counts.get(state, 0) for state in ("ISSUER_UNRESOLVED", "ISSUER_CONFLICTED", "ISSUER_QUARANTINED"))
    return {
        "phase": "3.6b.3e",
        "required_record_count": required,
        "record_count": len(planned),
        "completed_pilot_count": pilot_count,
        "batch_ready_security_count": counts.get("BATCH_READY", 0),
        "blocked_security_count": blocked,
        "issuer_batch_count": len(batches),
        "batch_state_counts": dict(sorted(counts.items())),
        "batch_plan_complete": blocked == 0 and counts.get("BATCH_READY", 0) + pilot_count == required,
        "next_required_step": "PRIORITY_BATCH_SOURCE_ACQUISITION_CONTROL" if blocked == 0 else "ISSUER_IDENTITY_EXCEPTION_REMEDIATION",
        "batches": batches,
        "records": planned,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {key: value for key, value in result.items() if key not in {"records", "batches"}}
    compact["top_batches"] = result["batches"][:25]
    compact["batch_plan_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
