from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "market_data_screen_policy.json"


class MarketDataScreenError(ValueError):
    """Raised when market-data screening violates governed requirements."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("phase") != "2" or policy.get("subphase") != "2B.1":
        raise MarketDataScreenError("Unexpected market-data screen phase")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise MarketDataScreenError("Evidence-determined sizing is required")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise MarketDataScreenError("Arbitrary universe targets are prohibited")
    if policy.get("preserve_input_universe") is not True:
        raise MarketDataScreenError("Input universe preservation is required")
    if policy.get("destructive_deletion_allowed") is not False:
        raise MarketDataScreenError("Destructive deletion is prohibited")
    if policy.get("fail_closed") is not True:
        raise MarketDataScreenError("Market-data screening must fail closed")
    authority = policy.get("authority", {})
    forbidden = (
        "analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    )
    if any(authority.get(key) is not False for key in forbidden):
        raise MarketDataScreenError("Market-data screening improperly expands authority")
    return policy


def _require_fields(record: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in record or record[field] is None]
    if missing:
        raise MarketDataScreenError(f"Missing required market evidence: {', '.join(missing)}")


def _validate_lineage(lineage: Any) -> None:
    if not isinstance(lineage, dict):
        raise MarketDataScreenError("Source lineage must be an object")
    for field in ("source_id", "retrieved_at_utc", "content_sha256"):
        if lineage.get(field) in (None, ""):
            raise MarketDataScreenError(f"Source lineage missing {field}")
    content_hash = str(lineage["content_sha256"])
    if len(content_hash) != 64 or any(character not in "0123456789abcdef" for character in content_hash):
        raise MarketDataScreenError("Source lineage content hash is invalid")


def screen_record(record: dict[str, Any], operating_date: date) -> dict[str, Any]:
    policy = load_policy()
    required = list(policy["required_evidence"])
    _require_fields(record, required)

    if record.get("processing_state") != policy["required_input_processing_state"]:
        raise MarketDataScreenError("Record is not in the active structural universe")

    start_date = date.fromisoformat(str(record["observation_start_date"]))
    end_date = date.fromisoformat(str(record["observation_end_date"]))
    if start_date > end_date:
        raise MarketDataScreenError("Observation start date is after end date")
    if end_date > operating_date:
        raise MarketDataScreenError("Future-dated market observations are prohibited")

    count = int(record["price_observation_count"])
    expected = int(record["expected_trading_session_count"])
    coverage = float(record["expected_session_coverage_ratio"])
    age = int(record["latest_observation_age_calendar_days"])
    adjusted = bool(record["adjusted_price_available"])
    median_dollar_volume = float(record["median_daily_dollar_volume_usd"])
    zero_volume_ratio = float(record["zero_volume_session_ratio"])
    conflict_state = str(record["corporate_action_conflict_state"])

    if count < 0 or expected <= 0:
        raise MarketDataScreenError("Observation counts are invalid")
    calculated_coverage = count / expected
    if abs(calculated_coverage - coverage) > 0.01:
        raise MarketDataScreenError("Reported session coverage does not reconcile")
    if not 0 <= coverage <= 1:
        raise MarketDataScreenError("Session coverage is outside the valid range")
    if age != (operating_date - end_date).days:
        raise MarketDataScreenError("Latest observation age does not reconcile")
    if median_dollar_volume < 0 or not 0 <= zero_volume_ratio <= 1:
        raise MarketDataScreenError("Liquidity evidence is invalid")
    if conflict_state not in {"CLEAR", "UNKNOWN", "CONFLICTED", "CRITICAL"}:
        raise MarketDataScreenError("Unknown corporate-action conflict state")
    _validate_lineage(record["source_lineage"])

    thresholds = policy["thresholds"]
    reasons: list[str] = []

    if conflict_state == "CRITICAL":
        state = "QUARANTINED"
        reasons.append("CRITICAL_CORPORATE_ACTION_CONFLICT")
    elif conflict_state in {"UNKNOWN", "CONFLICTED"}:
        state = "QUARANTINED"
        reasons.append("UNRESOLVED_CORPORATE_ACTION_EVIDENCE")
    elif not adjusted:
        state = "RESEARCH_ONLY"
        reasons.append("ADJUSTED_PRICE_UNAVAILABLE")
    elif age > int(thresholds["maximum_latest_observation_age_calendar_days"]):
        state = "RESEARCH_ONLY"
        reasons.append("STALE_MARKET_DATA")
    elif coverage < float(thresholds["minimum_expected_session_coverage_ratio"]):
        state = "RESEARCH_ONLY"
        reasons.append("INSUFFICIENT_SESSION_COVERAGE")
    elif (
        median_dollar_volume < float(thresholds["minimum_median_daily_dollar_volume_usd"])
        and zero_volume_ratio > float(thresholds["maximum_zero_volume_session_ratio"])
    ):
        state = "RESEARCH_ONLY"
        reasons.append("INSUFFICIENT_LIQUIDITY_EVIDENCE")
    elif count >= int(thresholds["minimum_full_history_observations"]):
        state = "MARKET_DATA_ELIGIBLE"
        reasons.append("FULL_MARKET_DATA_SCREEN_PASSED")
    elif count >= int(thresholds["minimum_provisional_history_observations"]):
        state = "MARKET_DATA_PROVISIONAL"
        reasons.append("LIMITED_HISTORY_PROVISIONAL")
    else:
        state = "RESEARCH_ONLY"
        reasons.append("INSUFFICIENT_HISTORY")

    result = deepcopy(record)
    result.update(
        {
            "screen_state": state,
            "screen_reasons": reasons,
            "analytics_authorized": False,
            "forecasting_authorized": False,
            "recommendations_authorized": False,
            "automatic_execution_authorized": False,
        }
    )
    return result


def screen_universe(records: list[dict[str, Any]], operating_date: date) -> dict[str, Any]:
    policy = load_policy()
    seen: set[str] = set()
    screened: list[dict[str, Any]] = []
    for record in records:
        security_id = record.get("security_id")
        if not security_id or security_id in seen:
            raise MarketDataScreenError("Market-data input requires unique stable security identities")
        seen.add(str(security_id))
        screened.append(screen_record(record, operating_date))

    symbols = {str(record.get("symbol")) for record in screened}
    missing_seeds = [symbol for symbol in policy["required_seed_symbols"] if symbol not in symbols]
    if missing_seeds:
        raise MarketDataScreenError(f"Required seed ETFs are missing: {', '.join(missing_seeds)}")

    counts: dict[str, int] = {}
    for record in screened:
        state = record["screen_state"]
        counts[state] = counts.get(state, 0) + 1

    return {
        "total_input_records": len(records),
        "screen_state_counts": dict(sorted(counts.items())),
        "records": screened,
        "selection_principle": policy["selection_principle"],
        "target_universe_size": None,
        "input_universe_preserved": True,
        "destructive_deletion_allowed": False,
        "required_seed_symbols": list(policy["required_seed_symbols"]),
    }
