from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class BrokerEligibilityError(ValueError):
    pass


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BrokerEligibilityError(f"Invalid timestamp: {field}") from exc
    if parsed.tzinfo is None:
        raise BrokerEligibilityError(f"Timestamp must be timezone-aware: {field}")
    return parsed.astimezone(timezone.utc)


def evaluate_broker_record(record: dict[str, Any], policy: dict[str, Any], as_of_utc: datetime) -> str:
    if policy.get("fail_closed") is not True:
        raise BrokerEligibilityError("Broker policy must fail closed")
    missing = set(policy.get("required_fields", [])) - set(record)
    if missing:
        raise BrokerEligibilityError(f"Missing broker fields: {sorted(missing)}")
    if record.get("broker_id") != policy.get("broker_id"):
        raise BrokerEligibilityError("Unexpected broker identity")
    if not str(record.get("security_id", "")).startswith("SEC-US-"):
        raise BrokerEligibilityError("Stable security identity is required")
    status = record.get("broker_status")
    if status not in policy.get("allowed_broker_statuses", []):
        raise BrokerEligibilityError("Unknown broker status")
    if record.get("verification_method") not in policy.get("allowed_verification_methods", []):
        raise BrokerEligibilityError("Unknown verification method")
    confidence = float(record.get("verification_confidence", -1))
    if confidence < float(policy.get("minimum_verification_confidence", 1)):
        return "BLOCKED"

    as_of = as_of_utc.astimezone(timezone.utc)
    verified = _parse_utc(record["verified_at_utc"], "verified_at_utc")
    effective = _parse_utc(record["effective_at_utc"], "effective_at_utc")
    available = _parse_utc(record["available_at_utc"], "available_at_utc")
    if available > as_of or effective > as_of or verified > as_of:
        raise BrokerEligibilityError("Future broker evidence is blocked")
    if available < effective:
        raise BrokerEligibilityError("Evidence cannot be available before effective")
    age_hours = (as_of - verified).total_seconds() / 3600
    if age_hours > float(policy.get("maximum_age_hours", 0)):
        return "STALE"

    if status in {"UNKNOWN", "CONFLICTED"}:
        return "QUARANTINED"
    if status != "ELIGIBLE":
        return "BLOCKED"
    if record.get("whole_share_supported") is not True:
        return "BLOCKED"
    return "BROKER_ELIGIBLE"


def build_broker_snapshot(records: list[dict[str, Any]], policy: dict[str, Any], as_of_utc: datetime) -> dict[str, Any]:
    seen: set[tuple[str, str]] = set()
    statuses: dict[str, str] = {}
    for record in records:
        key = (record.get("security_id", ""), record.get("broker_id", ""))
        if key in seen:
            raise BrokerEligibilityError("Duplicate security-broker record")
        seen.add(key)
        statuses[record["security_id"]] = evaluate_broker_record(record, policy, as_of_utc)
    return {
        "broker_id": policy["broker_id"],
        "as_of_utc": as_of_utc.astimezone(timezone.utc).isoformat(),
        "immutable": bool(policy.get("snapshot_immutable")),
        "statuses": statuses,
    }
