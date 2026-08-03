from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class NormalizationError(ValueError):
    """Raised when normalization or point-in-time rules fail."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise NormalizationError(f"Expected object in {path}")
    return data


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise NormalizationError(f"Invalid timestamp for {field}") from exc
    if parsed.tzinfo is None:
        raise NormalizationError(f"Timezone required for {field}")
    return parsed.astimezone(timezone.utc)


def validate_policy(policy: dict[str, Any]) -> None:
    required_true = [
        "fail_closed",
        "ticker_only_identity_blocked",
        "future_effective_records_blocked",
        "availability_before_effective_blocked",
        "silent_missing_value_imputation_forbidden",
        "provider_adjusted_reconciliation_required",
        "corporate_action_evidence_required",
        "conflicting_records_preserved",
        "critical_conflicts_quarantined",
    ]
    for field in required_true:
        if policy.get(field) is not True:
            raise NormalizationError(f"Policy must require {field}")
    if policy.get("input_zone") != "raw" or policy.get("output_zone") != "staged":
        raise NormalizationError("Normalization zones are invalid")
    if policy.get("quarantine_zone") != "quarantine":
        raise NormalizationError("Quarantine zone is invalid")
    if int(policy.get("adjusted_price_tolerance_bps", -1)) < 0:
        raise NormalizationError("Adjusted-price tolerance is invalid")
    for field in (
        "certified_market_monitoring_authorized",
        "certified_analytics_authorized",
        "direct_uip_database_writes_authorized",
    ):
        if policy.get(field) is not False:
            raise NormalizationError(f"Phase 1.3 cannot authorize {field}")


def validate_normalized_record(
    record: dict[str, Any],
    *,
    policy: dict[str, Any],
    known_security_ids: set[str],
    now_utc: datetime | None = None,
) -> None:
    validate_policy(policy)
    required = {
        "security_id",
        "domain",
        "source_id",
        "source_tier",
        "source_record_id",
        "observed_at_utc",
        "retrieved_at_utc",
        "content_sha256",
        "as_of_date",
        "effective_at_utc",
        "available_at_utc",
        "quality_status",
        "normalization_state",
    }
    missing = sorted(required - set(record))
    if missing:
        raise NormalizationError(f"Missing required fields: {missing}")
    security_id = str(record["security_id"])
    if security_id not in known_security_ids or security_id == str(record.get("ticker", "")):
        raise NormalizationError("Unknown or ticker-only security identity")
    if record["quality_status"] not in policy["allowed_quality_states"]:
        raise NormalizationError("Unknown quality state")
    if record["normalization_state"] not in {"STAGED", "QUARANTINED", "BLOCKED"}:
        raise NormalizationError("Unknown normalization state")
    observed = _parse_utc(record["observed_at_utc"], "observed_at_utc")
    retrieved = _parse_utc(record["retrieved_at_utc"], "retrieved_at_utc")
    effective = _parse_utc(record["effective_at_utc"], "effective_at_utc")
    available = _parse_utc(record["available_at_utc"], "available_at_utc")
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed > now or effective > now:
        raise NormalizationError("Future observation or effective timestamp")
    if retrieved < observed:
        raise NormalizationError("Retrieval precedes observation")
    if available < effective:
        raise NormalizationError("Availability precedes effective timestamp")
    digest = str(record["content_sha256"])
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise NormalizationError("Invalid content SHA-256")
    if record.get("imputed_fields"):
        raise NormalizationError("Silent missing-value imputation is forbidden")
    if record.get("critical_conflict") is True and record["normalization_state"] != "QUARANTINED":
        raise NormalizationError("Critical conflicts must be quarantined")


def reconcile_adjusted_price(
    provider_adjusted: float,
    reconstructed: float,
    *,
    tolerance_bps: int,
    corporate_action_evidence_present: bool,
) -> str:
    if provider_adjusted <= 0 or reconstructed <= 0:
        raise NormalizationError("Adjusted prices must be positive")
    if not corporate_action_evidence_present:
        raise NormalizationError("Corporate-action evidence is required")
    difference_bps = abs(provider_adjusted - reconstructed) / reconstructed * 10_000
    return "PASS" if difference_bps <= tolerance_bps else "QUARANTINED"
