from __future__ import annotations

from datetime import datetime, timezone


class AnalyticsEligibilityError(ValueError):
    pass


def evaluate_analytics_eligibility(record: dict, policy: dict, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    required_prior = set(policy["required_prior_states"])
    if not required_prior.issubset(set(record.get("prior_states", []))):
        return "BLOCKED"
    if record.get("critical_conflict") is True:
        return "QUARANTINED"
    if record.get("quality_status") in {"UNKNOWN", "CONFLICTED", "BLOCKED"}:
        return "QUARANTINED"
    if record.get("evidence_lineage_complete") is not True or record.get("point_in_time_complete") is not True:
        return "BLOCKED"
    evaluated = datetime.fromisoformat(record["evaluated_at_utc"].replace("Z", "+00:00"))
    if evaluated > now:
        return "BLOCKED"
    coverage = record.get("domain_coverage", {})
    missing = [d for d in policy["required_core_domains"] if not coverage.get(d, {}).get("present")]
    stale = [d for d in policy["required_core_domains"] if coverage.get(d, {}).get("freshness_status") not in {"CURRENT", "FRESH"}]
    if missing or stale:
        return "BLOCKED"
    history = int(record.get("price_history_trading_days", 0))
    if history < int(policy["minimum_price_history_trading_days"]):
        return "ANALYTICS_PROVISIONAL" if policy.get("new_funds_may_be_provisional") else "BLOCKED"
    specialized = record.get("specialized_product_type", "NONE")
    if specialized != "NONE" and policy.get("specialized_products_require_strategy_specific_coverage"):
        if record.get("strategy_specific_coverage_complete") is not True:
            return "BLOCKED"
    return "ANALYTICS_ELIGIBLE"


def validate_snapshot(records: list[dict]) -> None:
    seen: set[str] = set()
    for record in records:
        security_id = record.get("security_id")
        if security_id in seen:
            raise AnalyticsEligibilityError("Duplicate analytics eligibility record")
        seen.add(security_id)
