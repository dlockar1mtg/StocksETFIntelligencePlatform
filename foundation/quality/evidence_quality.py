from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceQualityError(ValueError):
    """Raised when evidence violates governed quality policy."""


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_quality_policy(policy: dict[str, Any]) -> None:
    if not policy.get("fail_closed"):
        raise EvidenceQualityError("quality policy must fail closed")
    if policy.get("minimum_completeness_for_pass") != 1.0:
        raise EvidenceQualityError("PASS requires complete evidence")
    if not policy.get("missing_evidence_reduces_confidence"):
        raise EvidenceQualityError("missing evidence must reduce confidence")
    if not policy.get("missing_evidence_cannot_be_rewarded"):
        raise EvidenceQualityError("missing evidence cannot be rewarded")
    if not policy.get("unknown_freshness_requires_quarantine"):
        raise EvidenceQualityError("unknown freshness must quarantine")
    if any(policy.get(key) for key in (
        "certified_market_monitoring_authorized",
        "certified_analytics_authorized",
        "direct_uip_database_writes_authorized",
    )):
        raise EvidenceQualityError("Phase 1.4 cannot expand authority")


def validate_evidence(record: dict[str, Any], policy: dict[str, Any]) -> None:
    validate_quality_policy(policy)
    missing = [field for field in policy["required_evidence_fields"] if field not in record]
    if missing:
        raise EvidenceQualityError(f"missing required evidence fields: {missing}")
    if record["domain"] not in policy["governed_domains"]:
        raise EvidenceQualityError("unknown evidence domain")
    if not str(record["security_id"]).startswith("SEC-"):
        raise EvidenceQualityError("ticker-only identity is forbidden")
    if not _SHA256.fullmatch(str(record["content_sha256"])):
        raise EvidenceQualityError("invalid SHA-256 lineage hash")

    quality = record["quality_status"]
    freshness = record["freshness_state"]
    if quality not in policy["allowed_quality_states"]:
        raise EvidenceQualityError("unknown quality status")
    if freshness not in policy["allowed_freshness_states"]:
        raise EvidenceQualityError("unknown freshness state")

    completeness = float(record["completeness_ratio"])
    confidence_impact = float(record["confidence_impact"])
    if not 0.0 <= completeness <= 1.0:
        raise EvidenceQualityError("completeness ratio must be between zero and one")
    if not -1.0 <= confidence_impact <= 0.0:
        raise EvidenceQualityError("confidence impact cannot reward evidence gaps")

    if quality == "PASS" and completeness < policy["minimum_completeness_for_pass"]:
        raise EvidenceQualityError("incomplete evidence cannot PASS")
    if quality == "PROVISIONAL" and completeness < policy["minimum_completeness_for_provisional"]:
        raise EvidenceQualityError("insufficient evidence cannot be PROVISIONAL")
    if completeness < 1.0 and confidence_impact >= 0.0:
        raise EvidenceQualityError("missing evidence must reduce confidence")
    if freshness == "UNKNOWN" and quality != "QUARANTINED":
        raise EvidenceQualityError("unknown freshness requires quarantine")
    if freshness == "STALE" and quality == "PASS":
        raise EvidenceQualityError("stale evidence cannot PASS")
    if record.get("critical_conflict", False) and quality != "QUARANTINED":
        raise EvidenceQualityError("critical conflicts require quarantine")
    if record.get("previous_quality_status") == "BLOCKED" and quality != "BLOCKED":
        raise EvidenceQualityError("blocked evidence cannot be promoted")
