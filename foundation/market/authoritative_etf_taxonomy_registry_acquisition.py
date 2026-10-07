from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class RegistryAcquisitionError(ValueError):
    """Raised when Phase 3.6b.3 acquisition evidence fails closed."""


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise RegistryAcquisitionError("INPUT_RECORD_ARRAY_MISSING")


def _valid_hash(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def build_acquisition_manifest(
    taxonomy_gap_document: Any,
    policy: dict[str, Any],
    existing_manifest: Any | None = None,
) -> dict[str, Any]:
    gaps = _records(taxonomy_gap_document)
    required = int(policy["required_record_count"])
    if len(gaps) != required:
        raise RegistryAcquisitionError("REQUIRED_RECORD_COUNT_MISMATCH")

    identities = [record.get("security_id") for record in gaps]
    if None in identities or len(set(identities)) != required:
        raise RegistryAcquisitionError("DUPLICATE_OR_MISSING_SECURITY_ID")

    existing_by_id: dict[str, dict[str, Any]] = {}
    if existing_manifest is not None:
        for record in _records(existing_manifest):
            security_id = record.get("security_id")
            if security_id in existing_by_id:
                raise RegistryAcquisitionError("DUPLICATE_EXISTING_MANIFEST_IDENTITY")
            existing_by_id[security_id] = record

    allowed_states = set(policy["acquisition_states"])
    allowed_tiers = set(policy["authoritative_source_tiers"])
    manifest_records: list[dict[str, Any]] = []

    for gap in gaps:
        security_id = gap["security_id"]
        symbol = gap.get("symbol")
        prior = existing_by_id.get(security_id)
        if prior is None:
            record = {
                "security_id": security_id,
                "symbol": symbol,
                "acquisition_state": "PENDING",
                "issuer_key": None,
                "source_tier": None,
                "source_id": None,
                "source_record_id": None,
                "source_url": None,
                "content_sha256": None,
                "captured_at_utc": None,
                "acquisition_reasons": ["AUTHORITATIVE_SOURCE_NOT_YET_CAPTURED"],
                "taxonomy_dimensions_assigned": False,
            }
        else:
            record = dict(prior)
            if record.get("security_id") != security_id or record.get("symbol") != symbol:
                raise RegistryAcquisitionError("MANIFEST_IDENTITY_MISMATCH")
            state = record.get("acquisition_state")
            if state not in allowed_states:
                raise RegistryAcquisitionError("INVALID_ACQUISITION_STATE")
            if record.get("taxonomy_dimensions_assigned") is not False:
                raise RegistryAcquisitionError("TAXONOMY_ASSIGNED_DURING_ACQUISITION")
            if state == "AUTHORITY_CAPTURED":
                if record.get("source_tier") not in allowed_tiers:
                    raise RegistryAcquisitionError("INVALID_AUTHORITATIVE_SOURCE_TIER")
                for field in (
                    "issuer_key",
                    "source_id",
                    "source_record_id",
                    "source_url",
                    "captured_at_utc",
                ):
                    if not record.get(field):
                        raise RegistryAcquisitionError(f"CAPTURED_AUTHORITY_MISSING_{field.upper()}")
                if not _valid_hash(record.get("content_sha256")):
                    raise RegistryAcquisitionError("CAPTURED_AUTHORITY_HASH_INVALID")
        manifest_records.append(record)

    state_counts = Counter(record["acquisition_state"] for record in manifest_records)
    issuer_counts = Counter(
        record["issuer_key"]
        for record in manifest_records
        if record.get("issuer_key")
    )
    captured = state_counts.get("AUTHORITY_CAPTURED", 0)
    return {
        "phase": "3.6b.3",
        "required_record_count": required,
        "record_count": len(manifest_records),
        "acquisition_state_counts": dict(sorted(state_counts.items())),
        "issuer_batch_counts": dict(sorted(issuer_counts.items())),
        "authority_captured_count": captured,
        "remaining_count": required - captured,
        "manifest_complete": captured == required,
        "next_required_step": (
            "PHASE_3_6B_2_TAXONOMY_NORMALIZATION_RERUN"
            if captured == required
            else "AUTHORITATIVE_SOURCE_CAPTURE_BY_ISSUER_BATCH"
        ),
        "records": manifest_records,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_payload = {key: value for key, value in result.items() if key != "records"}
    summary_payload["manifest_output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
