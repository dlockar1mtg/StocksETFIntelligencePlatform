from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "universe" / "structural_metadata_collection_policy.json"

SPECIALIZED_PATTERNS = {
    "LEVERAGED": [r"\b2x\b", r"\b3x\b", r"ultra", r"leveraged"],
    "INVERSE": [r"inverse", r"short", r"bear"],
    "SINGLE_STOCK": [r"single[- ]stock", r"daily .* bull", r"daily .* bear"],
    "VOLATILITY_LINKED": [r"volatility", r"vix"],
    "BUFFER_OR_DEFINED_OUTCOME": [r"buffer", r"defined outcome"],
    "COVERED_CALL_OR_OPTIONS_INCOME": [r"covered call", r"option income", r"buywrite"],
    "DERIVATIVE_HEAVY": [r"derivative", r"futures strategy", r"swap"],
    "COMMODITY_OR_FUTURES": [r"commodity", r"futures", r"crude oil", r"natural gas"],
    "CRYPTO_LINKED": [r"bitcoin", r"ether", r"crypto"],
    "ACTIVE_MANAGEMENT": [r"active", r"actively managed"],
}


class StructuralMetadataError(ValueError):
    """Raised when structural metadata violates governed requirements."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    if not path.exists():
        raise StructuralMetadataError(f"Structural metadata policy missing: {path}")
    policy = json.loads(path.read_text(encoding="utf-8"))
    validate_policy(policy)
    return policy


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("phase") != "2" or policy.get("subphase") != "2A.2":
        raise StructuralMetadataError("Unexpected structural metadata phase identity")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise StructuralMetadataError("Structural metadata collection may not impose a universe target")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise StructuralMetadataError("Evidence-determined sizing is required")
    if policy.get("preserve_full_discovery_universe") is not True:
        raise StructuralMetadataError("The discovery universe must remain preserved")
    if policy.get("raw_evidence_immutable") is not True or policy.get("fail_closed") is not True:
        raise StructuralMetadataError("Collection must preserve immutable raw evidence and fail closed")
    authority = policy.get("authority", {})
    forbidden = (
        "production_data_certification", "analytics_production", "forecasting", "ranking",
        "recommendations", "portfolio_allocation", "uip_export", "automatic_execution",
        "direct_uip_database_writes",
    )
    if any(authority.get(name) is not False for name in forbidden):
        raise StructuralMetadataError("Structural metadata policy improperly expands authority")


def content_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def classify_specialized_flags(*text_values: str | None) -> list[str]:
    text = " ".join(value or "" for value in text_values).lower()
    flags = {
        flag
        for flag, patterns in SPECIALIZED_PATTERNS.items()
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    }
    return sorted(flags)


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise StructuralMetadataError(f"Invalid {field}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise StructuralMetadataError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def validate_lineage(lineage: list[dict[str, Any]], now_utc: datetime | None = None) -> None:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not isinstance(lineage, list) or not lineage:
        raise StructuralMetadataError("At least one source-lineage record is required")
    for item in lineage:
        required = (
            "source_id", "dataset_id", "source_record_id", "retrieved_at_utc",
            "observed_at_utc", "authority_level", "source_status", "license_class",
            "content_sha256",
        )
        for field in required:
            if item.get(field) in (None, ""):
                raise StructuralMetadataError(f"Missing lineage field: {field}")
        retrieved = _parse_utc(item["retrieved_at_utc"], "retrieved_at_utc")
        observed = _parse_utc(item["observed_at_utc"], "observed_at_utc")
        if observed > retrieved or retrieved > now:
            raise StructuralMetadataError("Invalid lineage chronology")
        digest = item["content_sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise StructuralMetadataError("Lineage content hash must be lowercase SHA-256")
        if item["source_status"] not in {"research_only", "provisional", "certified", "deprecated", "blocked"}:
            raise StructuralMetadataError("Unknown source status")


def validate_record(record: dict[str, Any], now_utc: datetime | None = None) -> None:
    required = (
        "security_id", "symbol", "fund_name", "issuer_name", "instrument_structure",
        "fund_status", "inception_date", "strategy_description", "benchmark_name",
        "expense_ratio", "aum_usd", "specialized_flags", "observed_at_utc",
        "effective_date", "source_lineage", "record_status", "conflict_fields", "authority",
    )
    missing = [field for field in required if field not in record]
    if missing:
        raise StructuralMetadataError(f"Missing structural metadata fields: {missing}")
    if not record["security_id"] or not record["symbol"]:
        raise StructuralMetadataError("Stable security identity and symbol are required")
    policy = load_policy()
    if record["instrument_structure"] not in policy["allowed_instrument_structures"]:
        raise StructuralMetadataError("Unknown instrument structure")
    if record["fund_status"] not in policy["allowed_fund_statuses"]:
        raise StructuralMetadataError("Unknown fund status")
    if not isinstance(record["specialized_flags"], list):
        raise StructuralMetadataError("specialized_flags must be a list")
    unknown_flags = set(record["specialized_flags"]) - set(policy["specialized_flags"])
    if unknown_flags:
        raise StructuralMetadataError(f"Unknown specialized flags: {sorted(unknown_flags)}")
    if not isinstance(record["conflict_fields"], list):
        raise StructuralMetadataError("conflict_fields must be a list")
    if record["record_status"] not in {"COMPLETE", "PARTIAL", "CONFLICTED", "QUARANTINED", "BLOCKED"}:
        raise StructuralMetadataError("Unknown structural metadata status")
    observed = _parse_utc(record["observed_at_utc"], "observed_at_utc")
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed > now:
        raise StructuralMetadataError("Future structural metadata is prohibited")
    validate_lineage(record["source_lineage"], now)
    if record["conflict_fields"] and record["record_status"] not in {"CONFLICTED", "QUARANTINED", "BLOCKED"}:
        raise StructuralMetadataError("Conflicted fields must be preserved in a restricted state")
    if record["fund_status"] in {"CLOSING", "LIQUIDATING", "DELISTED"} and record["record_status"] != "BLOCKED":
        raise StructuralMetadataError("Closing, liquidating, and delisted funds must be blocked")
    authority = record["authority"]
    for field in (
        "analytics_authorized", "recommendations_authorized", "uip_export_authorized",
        "automatic_execution_authorized",
    ):
        if authority.get(field) is not False:
            raise StructuralMetadataError("Structural metadata records cannot grant downstream authority")


def normalize_record(raw: dict[str, Any], lineage: list[dict[str, Any]], observed_at_utc: str, effective_date: str) -> dict[str, Any]:
    name = raw.get("fund_name") or raw.get("name")
    strategy = raw.get("strategy_description") or raw.get("description")
    benchmark = raw.get("benchmark_name") or raw.get("benchmark")
    flags = sorted(set(raw.get("specialized_flags") or []) | set(classify_specialized_flags(name, strategy, benchmark)))
    record = {
        "security_id": raw.get("security_id"),
        "symbol": raw.get("symbol"),
        "fund_name": name,
        "issuer_name": raw.get("issuer_name") or raw.get("issuer"),
        "instrument_structure": raw.get("instrument_structure", "ETF"),
        "fund_status": raw.get("fund_status", "UNKNOWN"),
        "inception_date": raw.get("inception_date"),
        "strategy_description": strategy,
        "benchmark_name": benchmark,
        "expense_ratio": raw.get("expense_ratio"),
        "aum_usd": raw.get("aum_usd"),
        "specialized_flags": flags,
        "observed_at_utc": observed_at_utc,
        "effective_date": effective_date,
        "source_lineage": deepcopy(lineage),
        "record_status": "PARTIAL",
        "conflict_fields": [],
        "authority": {
            "analytics_authorized": False,
            "recommendations_authorized": False,
            "uip_export_authorized": False,
            "automatic_execution_authorized": False,
        },
    }
    complete_fields = ("fund_name", "issuer_name", "inception_date", "strategy_description")
    if all(record[field] not in (None, "") for field in complete_fields) and record["fund_status"] != "UNKNOWN":
        record["record_status"] = "COMPLETE"
    validate_record(record)
    return record


def reconcile_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for original in records:
        record = deepcopy(original)
        validate_record(record)
        grouped.setdefault(record["security_id"], []).append(record)
    reconciled: list[dict[str, Any]] = []
    comparable_fields = (
        "fund_name", "issuer_name", "instrument_structure", "fund_status", "inception_date",
        "strategy_description", "benchmark_name", "expense_ratio", "aum_usd",
    )
    for security_id, group in sorted(grouped.items()):
        base = deepcopy(group[0])
        conflicts: list[str] = []
        for field in comparable_fields:
            values = {json.dumps(item.get(field), sort_keys=True) for item in group if item.get(field) is not None}
            if len(values) > 1:
                conflicts.append(field)
        base["source_lineage"] = [line for item in group for line in item["source_lineage"]]
        base["specialized_flags"] = sorted({flag for item in group for flag in item["specialized_flags"]})
        base["conflict_fields"] = sorted(conflicts)
        if conflicts:
            base["record_status"] = "CONFLICTED"
        validate_record(base)
        reconciled.append(base)
    return reconciled


def summarize_coverage(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(records)
    for record in materialized:
        validate_record(record)
    fields = ("fund_name", "issuer_name", "inception_date", "strategy_description", "benchmark_name", "expense_ratio", "aum_usd")
    counts = {field: sum(record.get(field) not in (None, "") for record in materialized) for field in fields}
    statuses: dict[str, int] = {}
    for record in materialized:
        statuses[record["record_status"]] = statuses.get(record["record_status"], 0) + 1
    return {
        "total_records": len(materialized),
        "field_coverage_counts": counts,
        "record_status_counts": dict(sorted(statuses.items())),
        "target_universe_size": None,
        "selection_principle": "EVIDENCE_DETERMINES_SIZE",
    }
