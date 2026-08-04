from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ETFDiscoveryError(ValueError):
    """Raised when an ETF discovery record violates governed policy."""


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ETFDiscoveryError("Invalid UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise ETFDiscoveryError("Timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def validate_discovery_policy(policy: dict[str, Any]) -> None:
    if policy.get("phase") != "1.6.2" or policy.get("fail_closed") is not True:
        raise ETFDiscoveryError("Discovery policy must govern Phase 1.6.2 and fail closed")
    if policy.get("required_instrument_type") != "ETF":
        raise ETFDiscoveryError("ETF must be the required instrument type")
    if policy.get("minimum_independent_authorities", 0) < 2:
        raise ETFDiscoveryError("At least two independent authorities are required")
    for key in (
        "sec_or_exchange_authority_required",
        "identity_conflicts_preserved",
        "instrument_type_conflicts_quarantined",
        "ticker_reuse_requires_new_security_id",
        "symbol_changes_require_history",
        "future_available_records_blocked",
        "unknown_listing_status_blocked",
        "snapshot_required",
        "snapshot_immutable",
    ):
        if policy.get(key) is not True:
            raise ETFDiscoveryError(f"Required discovery control weakened: {key}")
    if policy.get("broker_eligibility_inferred_from_listing") is not False:
        raise ETFDiscoveryError("Broker eligibility cannot be inferred from listing")
    if policy.get("analytics_eligibility_inferred_from_listing") is not False:
        raise ETFDiscoveryError("Analytics eligibility cannot be inferred from listing")


def validate_discovery_record(
    record: dict[str, Any], policy: dict[str, Any], *, as_of_utc: datetime | None = None
) -> dict[str, Any]:
    validate_discovery_policy(policy)
    required = set(policy["required_identity_fields"])
    missing = required - set(record)
    if missing:
        raise ETFDiscoveryError(f"Missing discovery fields: {sorted(missing)}")
    if not str(record["security_id"]).startswith("SEC-US-"):
        raise ETFDiscoveryError("Stable US security identity is required")
    if record["instrument_type"] != "ETF":
        raise ETFDiscoveryError("Non-ETF instruments must use a separate registry")
    if record["primary_exchange"] not in policy["allowed_primary_exchanges"]:
        raise ETFDiscoveryError("Unsupported primary exchange")
    if record["listing_status"] not in policy["listing_states"]:
        raise ETFDiscoveryError("Unknown listing state")
    if record["listing_status"] == "UNKNOWN":
        raise ETFDiscoveryError("Unknown listing status must be blocked")
    sources = record["source_ids"]
    if not isinstance(sources, list) or len(set(sources)) < policy["minimum_independent_authorities"]:
        raise ETFDiscoveryError("Insufficient independent listing authorities")
    if not any(str(source).startswith(("SEC-", "NYSE-", "NASDAQ-", "CBOE-")) for source in sources):
        raise ETFDiscoveryError("SEC or primary-exchange authority is required")
    digest = str(record["content_sha256"])
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ETFDiscoveryError("Invalid SHA-256 evidence digest")
    effective = _parse_utc(record["effective_at_utc"])
    available = _parse_utc(record["available_at_utc"])
    if available < effective:
        raise ETFDiscoveryError("Availability cannot precede effective time")
    now = (as_of_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if available > now:
        raise ETFDiscoveryError("Future-available discovery records are blocked")
    quarantine = list(record.get("quarantine_reasons", []))
    active = record["listing_status"] == "ACTIVE" and not quarantine
    return {
        "security_id": record["security_id"],
        "listing_status": record["listing_status"],
        "discovery_state": "DISCOVERED" if active else "QUARANTINED",
        "active_listing": active,
        "broker_eligible": False,
        "analytics_eligible": False,
    }


def build_snapshot(records: list[dict[str, Any]], policy: dict[str, Any], *, snapshot_id: str) -> dict[str, Any]:
    validate_discovery_policy(policy)
    if not snapshot_id:
        raise ETFDiscoveryError("Snapshot ID is required")
    seen: set[str] = set()
    accepted: list[str] = []
    quarantined: list[str] = []
    for record in records:
        security_id = str(record.get("security_id", ""))
        if security_id in seen:
            raise ETFDiscoveryError("Duplicate security identity in snapshot")
        seen.add(security_id)
        result = validate_discovery_record(record, policy)
        (accepted if result["active_listing"] else quarantined).append(security_id)
    return {
        "snapshot_id": snapshot_id,
        "immutable": True,
        "record_count": len(records),
        "active_security_ids": sorted(accepted),
        "quarantined_security_ids": sorted(quarantined),
    }
