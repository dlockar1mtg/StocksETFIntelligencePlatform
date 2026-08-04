from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "universe" / "etf_structural_triage_policy.json"

ALLOWED_STATES = {
    "STRUCTURAL_CANDIDATE",
    "DATA_COLLECTION_CANDIDATE",
    "ANALYTICS_PROVISIONAL",
    "SPECIALIZED",
    "PORTFOLIO_RESTRICTED",
    "RESEARCH_ONLY",
    "QUARANTINED",
    "BLOCKED",
}

BLOCKING_BROKER_STATUSES = {
    "PURCHASE_RESTRICTED",
    "SELL_ONLY",
    "TEMPORARILY_UNAVAILABLE",
    "DELISTED",
    "UNKNOWN",
    "CONFLICTED",
}

BLOCKED_STRUCTURES = {"ETN", "CEF"}
SPECIALIZED_FLAGS = {
    "LEVERAGED",
    "INVERSE",
    "SINGLE_STOCK",
    "VOLATILITY_LINKED",
    "BUFFER_OR_DEFINED_OUTCOME",
    "COVERED_CALL_OR_OPTIONS_INCOME",
    "DERIVATIVE_HEAVY",
    "COMMODITY_OR_FUTURES",
    "CRYPTO_LINKED",
    "ACTIVE_MANAGEMENT",
    "NEW_OR_INSUFFICIENT_HISTORY",
    "ILLIQUID_OR_STALE",
    "CLOSING_OR_LIQUIDATING",
}


class StructuralTriageError(ValueError):
    """Raised when structural triage evidence violates a governed rule."""


@dataclass(frozen=True)
class TriageSummary:
    total_records: int
    counts_by_state: dict[str, int]
    counts_by_cost_tier: dict[str, int]
    target_universe_size: None
    selection_principle: str


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    if not path.exists():
        raise StructuralTriageError(f"Structural triage policy missing: {path}")
    policy = json.loads(path.read_text(encoding="utf-8"))
    validate_policy(policy)
    return policy


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("phase") != "2" or policy.get("subphase") != "2A":
        raise StructuralTriageError("Unexpected structural triage phase identity")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise StructuralTriageError("Structural triage may not impose a target universe size")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise StructuralTriageError("Evidence-determined sizing is required")
    if policy.get("preserve_full_discovery_universe") is not True:
        raise StructuralTriageError("The full discovery universe must remain preserved")
    if policy.get("destructive_deletion_allowed") is not False:
        raise StructuralTriageError("Destructive universe deletion is prohibited")
    if set(policy.get("triage_states", [])) != ALLOWED_STATES:
        raise StructuralTriageError("Governed triage states drifted")
    authority = policy.get("authority", {})
    forbidden = {
        "analytics_production",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    }
    if any(authority.get(name) is not False for name in forbidden):
        raise StructuralTriageError("Structural triage improperly grants downstream authority")
    if policy.get("fail_closed") is not True:
        raise StructuralTriageError("Structural triage must fail closed")


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise StructuralTriageError(f"Invalid {field_name}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise StructuralTriageError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _require_nonempty(record: dict[str, Any], field: str) -> None:
    value = record.get(field)
    if value is None or value == "" or value == []:
        raise StructuralTriageError(f"Missing required triage field: {field}")


def validate_record(record: dict[str, Any], now_utc: datetime | None = None) -> None:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    required = [
        "security_id",
        "symbol",
        "broker_status",
        "instrument_structure",
        "specialized_flags",
        "fund_status",
        "liquidity_status",
        "identity_quality_status",
        "evidence_quality_status",
        "conflict_status",
        "triage_state",
        "reason_codes",
        "cost_tier",
        "observed_at_utc",
        "effective_date",
        "source_lineage",
        "authority",
    ]
    for field in required:
        _require_nonempty(record, field)

    state = record["triage_state"]
    if state not in ALLOWED_STATES:
        raise StructuralTriageError(f"Unknown triage state: {state}")

    unknown_flags = set(record["specialized_flags"]) - SPECIALIZED_FLAGS
    if unknown_flags:
        raise StructuralTriageError(f"Unknown specialized flags: {sorted(unknown_flags)}")

    observed = _parse_utc(record["observed_at_utc"], "observed_at_utc")
    if observed > now:
        raise StructuralTriageError("Future triage observations are prohibited")

    lineage = record["source_lineage"]
    if not isinstance(lineage, list) or not lineage:
        raise StructuralTriageError("At least one lineage record is required")
    for item in lineage:
        for field in (
            "source_id",
            "dataset_id",
            "source_record_id",
            "retrieved_at_utc",
            "observed_at_utc",
            "authority_level",
            "source_status",
            "license_class",
            "content_sha256",
        ):
            _require_nonempty(item, field)
        retrieved = _parse_utc(item["retrieved_at_utc"], "retrieved_at_utc")
        source_observed = _parse_utc(item["observed_at_utc"], "source observed_at_utc")
        if source_observed > retrieved or retrieved > now:
            raise StructuralTriageError("Invalid lineage chronology")
        content_hash = item["content_sha256"]
        if len(content_hash) != 64 or any(c not in "0123456789abcdef" for c in content_hash):
            raise StructuralTriageError("Lineage content hash must be lowercase SHA-256")
        if item["source_status"] in {"blocked", "deprecated"} and state not in {"QUARANTINED", "BLOCKED", "RESEARCH_ONLY"}:
            raise StructuralTriageError("Blocked or deprecated evidence cannot support promotion")

    authority = record["authority"]
    if any(authority.get(key) is not False for key in (
        "analytics_authorized",
        "recommendations_authorized",
        "uip_export_authorized",
        "automatic_execution_authorized",
    )):
        raise StructuralTriageError("A triage record cannot grant downstream authority")

    if record["broker_status"] in BLOCKING_BROKER_STATUSES and state != "BLOCKED":
        raise StructuralTriageError("Broker-ineligible records must remain BLOCKED")
    if record["instrument_structure"] in BLOCKED_STRUCTURES and state not in {"BLOCKED", "RESEARCH_ONLY"}:
        raise StructuralTriageError("ETNs and CEFs require separate approval")
    if record["fund_status"] in {"CLOSING", "LIQUIDATING", "DELISTED"} and state != "BLOCKED":
        raise StructuralTriageError("Closing, liquidating, or delisted funds must be BLOCKED")
    if record["identity_quality_status"] in {"QUARANTINED", "BLOCKED"} and state not in {"QUARANTINED", "BLOCKED"}:
        raise StructuralTriageError("Identity defects cannot be promoted")
    if record["conflict_status"] == "UNRESOLVED_CRITICAL" and state not in {"QUARANTINED", "BLOCKED"}:
        raise StructuralTriageError("Decision-critical conflicts must block promotion")
    if record["evidence_quality_status"] in {"STALE", "CONFLICTED", "BLOCKED"} and state not in {"QUARANTINED", "BLOCKED", "RESEARCH_ONLY"}:
        raise StructuralTriageError("Stale or conflicted evidence cannot support promotion")
    if "NEW_OR_INSUFFICIENT_HISTORY" in record["specialized_flags"] and state == "ANALYTICS_PROVISIONAL":
        pass
    elif "NEW_OR_INSUFFICIENT_HISTORY" in record["specialized_flags"] and state in {"STRUCTURAL_CANDIDATE", "DATA_COLLECTION_CANDIDATE"}:
        raise StructuralTriageError("Insufficient-history funds must remain provisional, specialized, restricted, or research-only")
    if set(record["specialized_flags"]) & {"LEVERAGED", "INVERSE", "SINGLE_STOCK"} and state not in {"SPECIALIZED", "PORTFOLIO_RESTRICTED", "RESEARCH_ONLY", "BLOCKED"}:
        raise StructuralTriageError("Leveraged, inverse, and single-stock funds require specialized treatment")


def summarize_records(records: Iterable[dict[str, Any]]) -> TriageSummary:
    policy = load_policy()
    seen_security_ids: set[str] = set()
    counts_by_state = {state: 0 for state in sorted(ALLOWED_STATES)}
    counts_by_cost_tier: dict[str, int] = {}
    total = 0
    for original in records:
        record = deepcopy(original)
        validate_record(record)
        security_id = record["security_id"]
        if security_id in seen_security_ids:
            raise StructuralTriageError(f"Duplicate security_id in triage snapshot: {security_id}")
        seen_security_ids.add(security_id)
        counts_by_state[record["triage_state"]] += 1
        tier = record["cost_tier"]
        counts_by_cost_tier[tier] = counts_by_cost_tier.get(tier, 0) + 1
        total += 1
    return TriageSummary(
        total_records=total,
        counts_by_state=counts_by_state,
        counts_by_cost_tier=dict(sorted(counts_by_cost_tier.items())),
        target_universe_size=None,
        selection_principle=policy["selection_principle"],
    )
