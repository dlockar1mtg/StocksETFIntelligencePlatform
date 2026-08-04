from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "historical_data_authority_policy.json"
REGISTRY_PATH = ROOT / "config" / "contracts" / "contract_registry.json"


class HistoricalDataAuthorityError(ValueError):
    """Raised when Phase 3.1 historical-data authority is violated."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("phase") != "3" or policy.get("subphase") != "3.1":
        raise HistoricalDataAuthorityError("Unexpected historical-data phase")
    if policy.get("required_candidate_count") != 3462:
        raise HistoricalDataAuthorityError("Certified candidate count drifted")
    if policy.get("required_candidate_state") != "MARKET_DATA_ELIGIBLE":
        raise HistoricalDataAuthorityError("Candidate admission state drifted")
    if policy.get("provisional_candidates_allowed") is not False:
        raise HistoricalDataAuthorityError("Provisional candidates are not authorized")
    if policy.get("fail_closed") is not True:
        raise HistoricalDataAuthorityError("Historical-data authority must fail closed")
    forbidden = (
        "return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    )
    authority = policy.get("authority", {})
    if any(authority.get(key) is not False for key in forbidden):
        raise HistoricalDataAuthorityError("Phase 3.1 improperly expands downstream authority")
    return policy


def validate_candidate_universe(document: dict[str, Any]) -> list[dict[str, Any]]:
    policy = load_policy()
    records = list(document.get("records") or [])
    if document.get("record_count") != policy["required_candidate_count"]:
        raise HistoricalDataAuthorityError("Candidate document count drifted")
    if len(records) != policy["required_candidate_count"]:
        raise HistoricalDataAuthorityError("Candidate record array count drifted")
    if document.get("admission_state") != policy["required_candidate_state"]:
        raise HistoricalDataAuthorityError("Candidate admission state is invalid")
    if document.get("provisional_records_included") is not False:
        raise HistoricalDataAuthorityError("Provisional candidates were included")

    seen: set[str] = set()
    symbols: set[str] = set()
    for record in records:
        security_id = str(record.get("security_id") or "")
        symbol = str(record.get("symbol") or "")
        if not security_id or security_id in seen:
            raise HistoricalDataAuthorityError("Stable security identities must be unique")
        if record.get("screen_state") != policy["required_candidate_state"]:
            raise HistoricalDataAuthorityError("Noneligible record entered Phase 3")
        seen.add(security_id)
        symbols.add(symbol)

    missing = [symbol for symbol in policy["required_seed_symbols"] if symbol not in symbols]
    if missing:
        raise HistoricalDataAuthorityError(f"Required seed ETFs are missing: {', '.join(missing)}")
    return records


def validate_observation(record: dict[str, Any], operating_date: date) -> dict[str, Any]:
    policy = load_policy()
    required = (
        "security_id", "symbol", "provider_id", "provider_symbol",
        "observation_date", "available_at_utc", "adjusted_close",
        "return_basis", "corporate_action_state", "source_lineage", "authority",
    )
    missing = [field for field in required if record.get(field) is None]
    if missing:
        raise HistoricalDataAuthorityError(f"Missing required observation evidence: {', '.join(missing)}")

    if record["provider_id"] != policy["provider_authority"]["primary_provider_id"]:
        raise HistoricalDataAuthorityError("Unknown or unauthorized provider")
    if str(record["symbol"]).upper() != str(record["provider_symbol"]).upper():
        raise HistoricalDataAuthorityError("Provider symbol mismatch")
    observation_date = date.fromisoformat(str(record["observation_date"]))
    if observation_date > operating_date:
        raise HistoricalDataAuthorityError("Future-dated observation is prohibited")
    available = datetime.fromisoformat(str(record["available_at_utc"]).replace("Z", "+00:00"))
    if available.date() < observation_date:
        raise HistoricalDataAuthorityError("Availability precedes observation date")
    if record["return_basis"] != policy["return_basis"]["primary_basis"]:
        raise HistoricalDataAuthorityError("Total-return basis is required")
    if record["corporate_action_state"] in {"CONFLICTED", "CRITICAL", "UNKNOWN"}:
        raise HistoricalDataAuthorityError("Unresolved corporate-action evidence must quarantine")

    lineage = record["source_lineage"]
    for field in ("source_url", "raw_path", "content_sha256", "retrieved_at_utc"):
        if not isinstance(lineage, dict) or not lineage.get(field):
            raise HistoricalDataAuthorityError(f"Source lineage missing {field}")
    digest = str(lineage["content_sha256"])
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise HistoricalDataAuthorityError("Source lineage hash is invalid")

    authority = record["authority"]
    if authority.get("normalization") is not True:
        raise HistoricalDataAuthorityError("Normalization authority is required")
    for key in ("return_calculation", "risk_analytics", "forecasting", "recommendations", "automatic_execution"):
        if authority.get(key) is not False:
            raise HistoricalDataAuthorityError("Observation improperly expands authority")
    return record


def validate_contract_registration() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    matches = [
        item for item in registry.get("contracts", [])
        if item.get("contract_id") == "native.historical_market_data_observation"
    ]
    if len(matches) != 1:
        raise HistoricalDataAuthorityError("Historical observation contract is not uniquely registered")
    item = matches[0]
    if item.get("version") != "1.0.0" or item.get("status") != "ACTIVE":
        raise HistoricalDataAuthorityError("Historical observation contract registration drifted")
    if not (ROOT / str(item.get("schema"))).exists():
        raise HistoricalDataAuthorityError("Historical observation schema is missing")
