from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from foundation.validation.contracts import load_json


class MarketStandardValidationError(ValueError):
    pass


def validate_market_calendar(document: dict[str, Any]) -> None:
    required = {
        "calendar_id",
        "timezone",
        "session_definition",
        "weekmask",
        "holiday_source_tier_required",
        "unknown_calendar_dates_blocked",
        "early_close_requires_explicit_record",
        "non_trading_days_generate_returns",
        "as_of_date_required",
    }
    if set(document) != required:
        raise MarketStandardValidationError("Market calendar fields must match the governed contract exactly.")
    if document["timezone"] != "America/New_York":
        raise MarketStandardValidationError("US ETF market calendar must use America/New_York.")
    if document["weekmask"] != ["MON", "TUE", "WED", "THU", "FRI"]:
        raise MarketStandardValidationError("Unexpected market weekmask.")
    if document["holiday_source_tier_required"] != 1:
        raise MarketStandardValidationError("Holiday authority must be Tier 1.")
    if not document["unknown_calendar_dates_blocked"] or not document["early_close_requires_explicit_record"]:
        raise MarketStandardValidationError("Calendar controls must fail closed.")
    if document["non_trading_days_generate_returns"]:
        raise MarketStandardValidationError("Non-trading days cannot generate returns.")


def validate_return_standard(document: dict[str, Any]) -> None:
    if document.get("security_return_basis") != "total_return":
        raise MarketStandardValidationError("Security returns must use total return.")
    if document.get("benchmark_return_basis") != "total_return":
        raise MarketStandardValidationError("Benchmark returns must use total return.")
    if document.get("price_return_allowed_for_certified_comparison") is not False:
        raise MarketStandardValidationError("Price return cannot be used for certified comparisons.")
    if document.get("split_adjustment_required") is not True:
        raise MarketStandardValidationError("Split adjustment is required.")
    if document.get("annualization_day_count") != 252:
        raise MarketStandardValidationError("Annualization must use 252 trading days.")
    for key in ("missing_return_observations", "mixed_return_bases", "look_ahead_data"):
        if document.get(key) != "BLOCK":
            raise MarketStandardValidationError(f"{key} must be blocked.")


def validate_corporate_action_policy(document: dict[str, Any]) -> None:
    required_actions = {
        "CASH_DISTRIBUTION",
        "SPLIT",
        "REVERSE_SPLIT",
        "SYMBOL_CHANGE",
        "FUND_MERGER",
        "LIQUIDATION",
    }
    if set(document.get("supported_actions", [])) != required_actions:
        raise MarketStandardValidationError("Corporate action set is incomplete.")
    if document.get("source_tier_maximum") not in {1, 2}:
        raise MarketStandardValidationError("Corporate actions require Tier 1 or Tier 2 evidence.")
    required_true = (
        "effective_date_required",
        "announcement_date_required",
        "point_in_time_enforcement",
        "unknown_actions_blocked",
        "conflicting_actions_quarantined",
        "manual_override_requires_evidence",
    )
    if not all(document.get(key) is True for key in required_true):
        raise MarketStandardValidationError("Corporate-action controls must fail closed.")
    if document.get("retroactive_silent_rewrite") is not False:
        raise MarketStandardValidationError("Silent retroactive rewrites are prohibited.")


def validate_point_in_time_action(record: dict[str, Any], as_of_date: str) -> None:
    try:
        as_of = date.fromisoformat(as_of_date)
        announced = date.fromisoformat(record["announcement_date"])
        effective = date.fromisoformat(record["effective_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketStandardValidationError("Corporate action dates must be valid ISO dates.") from exc
    if announced > as_of:
        raise MarketStandardValidationError("Action was not known as of the requested date.")
    if effective < announced:
        raise MarketStandardValidationError("Effective date cannot precede announcement date.")


def load_and_validate_market_controls(root: Path) -> None:
    calendar = load_json(root / "config/market/market_calendar.json")
    returns = load_json(root / "config/market/return_standard.json")
    actions = load_json(root / "config/market/corporate_action_policy.json")
    validate_market_calendar(calendar)
    validate_return_standard(returns)
    validate_corporate_action_policy(actions)
