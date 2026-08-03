from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from foundation.validation.contracts import ContractValidationError, load_json


class SourceValidationError(ContractValidationError):
    pass


def validate_source_authority(document: dict[str, Any]) -> None:
    required = {"version", "unknown_sources_blocked", "source_conflicts_preserved", "silent_conflict_resolution_forbidden", "restricted_data_must_remain_outside_git", "tiers"}
    if set(document) != required:
        raise SourceValidationError("Source authority keys do not match the governed contract")
    if not all(document[key] for key in required - {"version", "tiers"}):
        raise SourceValidationError("Source authority must fail closed")
    tiers = document["tiers"]
    if [item["tier"] for item in tiers] != [1, 2, 3, 4, 5]:
        raise SourceValidationError("Source tiers must be ordered 1 through 5")
    if len({item["id"] for item in tiers}) != 5:
        raise SourceValidationError("Source tier identifiers must be unique")


def validate_data_zones(document: dict[str, Any]) -> None:
    zone_ids = [item["id"] for item in document.get("zones", [])]
    if zone_ids != ["raw", "staged", "curated", "evidence", "quarantine"]:
        raise SourceValidationError("Required data zones are missing or out of order")
    by_id = {item["id"]: item for item in document["zones"]}
    if by_id["raw"]["mutable"] or by_id["evidence"]["mutable"]:
        raise SourceValidationError("Raw and evidence zones must be immutable")
    if not document.get("raw_records_must_not_be_overwritten"):
        raise SourceValidationError("Raw overwrite protection must remain enabled")
    if not document.get("conflicted_records_must_be_quarantined"):
        raise SourceValidationError("Conflicted records must be quarantined")


def validate_lineage(record: dict[str, Any], required_fields: list[str]) -> None:
    missing = [field for field in required_fields if not record.get(field)]
    if missing:
        raise SourceValidationError(f"Missing lineage fields: {', '.join(missing)}")
    digest = record["content_sha256"]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise SourceValidationError("content_sha256 must be a lowercase SHA-256 digest")
    observed = datetime.fromisoformat(record["observed_at_utc"].replace("Z", "+00:00"))
    ingested = datetime.fromisoformat(record["ingested_at_utc"].replace("Z", "+00:00"))
    if observed.tzinfo is None or ingested.tzinfo is None:
        raise SourceValidationError("Lineage timestamps must include timezone information")
    if observed > ingested:
        raise SourceValidationError("Observation time cannot follow ingestion time")


def freshness_state(observed_at_utc: str, current_at_utc: str, aging_hours: int, stale_hours: int) -> str:
    if aging_hours < 0 or stale_hours <= aging_hours:
        raise SourceValidationError("Freshness thresholds are invalid")
    try:
        observed = datetime.fromisoformat(observed_at_utc.replace("Z", "+00:00"))
        current = datetime.fromisoformat(current_at_utc.replace("Z", "+00:00"))
    except ValueError:
        return "UNKNOWN"
    age_hours = (current - observed).total_seconds() / 3600
    if age_hours < 0:
        return "UNKNOWN"
    if age_hours <= aging_hours:
        return "CURRENT"
    if age_hours <= stale_hours:
        return "AGING"
    return "STALE"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_governed_source_controls(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    authority = load_json(root / "config/sources/source_authority.json")
    zones = load_json(root / "config/data/data_zones.json")
    validate_source_authority(authority)
    validate_data_zones(zones)
    return authority, zones
