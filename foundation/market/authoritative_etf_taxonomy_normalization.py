from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class AuthoritativeTaxonomyError(ValueError):
    """Raised when Phase 3.6b.2 normalization evidence fails closed."""


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise AuthoritativeTaxonomyError("EVIDENCE_RECORD_ARRAY_MISSING")


def _valid_hash(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return len(set(value.lower())) > 1


def _lineage_valid(entry: dict[str, Any], policy: dict[str, Any]) -> bool:
    return (
        entry.get("source_tier") in set(policy["authoritative_source_tiers"])
        and bool(entry.get("source_id"))
        and bool(entry.get("source_record_id"))
        and _valid_hash(entry.get("content_sha256"))
    )


def normalize_taxonomy_record(
    evidence: dict[str, Any],
    registry_entry: dict[str, Any] | list[dict[str, Any]] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    security_id = evidence.get("security_id")
    symbol = evidence.get("symbol")
    if not security_id:
        raise AuthoritativeTaxonomyError("STABLE_SECURITY_ID_MISSING")

    base = {
        "security_id": security_id,
        "symbol": symbol,
        "classification_status": "UNKNOWN",
        "classification_reasons": [],
        "asset_class": None,
        "strategy": None,
        "geography": None,
        "market_segment": None,
        "income_profile": None,
        "implementation": None,
        "specialized_product_type": None,
        "portfolio_treatment": None,
        "classified_at_utc": None,
        "source_id": None,
        "source_record_id": None,
        "content_sha256": None,
        "secondary_evidence_lineage": {
            "collection_state": evidence.get("collection_state"),
            "provider_symbol": evidence.get("provider_symbol"),
            "provider_payload_sha256": evidence.get("provider_payload_sha256"),
            "retrieved_at_utc": evidence.get("retrieved_at_utc"),
        },
        "taxonomy_classification_authorized": False,
    }

    if evidence.get("collection_state") != "COLLECTED":
        base["classification_reasons"].append("SECONDARY_EVIDENCE_NOT_COLLECTED")
        return base

    if registry_entry is None:
        base["classification_reasons"].append("AUTHORITATIVE_REGISTRY_ENTRY_MISSING")
        return base

    candidates = registry_entry if isinstance(registry_entry, list) else [registry_entry]
    if len(candidates) != 1:
        base["classification_status"] = "CONFLICTED"
        base["classification_reasons"].append("MULTIPLE_AUTHORITATIVE_CLASSIFICATIONS")
        return base

    entry = candidates[0]
    if entry.get("symbol") and str(entry["symbol"]).upper() != str(symbol).upper():
        base["classification_status"] = "CONFLICTED"
        base["classification_reasons"].append("AUTHORITATIVE_SYMBOL_MISMATCH")
        return base

    if not _lineage_valid(entry, policy):
        base["classification_status"] = "QUARANTINED"
        base["classification_reasons"].append("AUTHORITATIVE_LINEAGE_INVALID")
        return base

    missing = [field for field in policy["required_dimensions"] if not entry.get(field)]
    if missing:
        base["classification_status"] = "QUARANTINED"
        base["classification_reasons"].append("REQUIRED_DIMENSIONS_MISSING")
        base["classification_reasons"].extend(f"MISSING_{field.upper()}" for field in missing)
        return base

    for field in policy["required_dimensions"]:
        base[field] = entry[field]
    base.update({
        "classification_status": "CLASSIFIED",
        "classified_at_utc": entry.get("classified_at_utc"),
        "source_id": entry["source_id"],
        "source_record_id": entry["source_record_id"],
        "content_sha256": entry["content_sha256"],
        "taxonomy_classification_authorized": True,
    })
    return base


def build_taxonomy_snapshot(
    evidence_document: Any,
    registry_document: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    evidence_records = _records(evidence_document)
    required = int(policy["required_record_count"])
    if len(evidence_records) != required:
        raise AuthoritativeTaxonomyError("REQUIRED_RECORD_COUNT_MISMATCH")

    identities = [record.get("security_id") for record in evidence_records]
    if None in identities or len(set(identities)) != required:
        raise AuthoritativeTaxonomyError("DUPLICATE_OR_MISSING_SECURITY_ID")

    registry = registry_document.get("records", {})
    records = [
        normalize_taxonomy_record(record, registry.get(record["security_id"]), policy)
        for record in evidence_records
    ]
    state_counts = Counter(record["classification_status"] for record in records)
    reason_counts = Counter(
        reason for record in records for reason in record.get("classification_reasons", [])
    )
    certified = (
        state_counts.get("CLASSIFIED", 0) == required
        and sum(state_counts.get(state, 0) for state in ("UNKNOWN", "CONFLICTED", "QUARANTINED")) == 0
    )
    return {
        "phase": "3.6b.2",
        "required_record_count": required,
        "record_count": len(records),
        "classification_state_counts": dict(sorted(state_counts.items())),
        "classification_reason_counts": dict(sorted(reason_counts.items())),
        "taxonomy_snapshot_certified": certified,
        "next_required_step": (
            "PHASE_3_6B_FULL_UNIVERSE_BENCHMARK_ASSIGNMENT"
            if certified
            else "AUTHORITATIVE_REGISTRY_REMEDIATION"
        ),
        "records": records,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_payload = {key: value for key, value in result.items() if key != "records"}
    summary_payload["taxonomy_output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
