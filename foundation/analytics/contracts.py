from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PILLARS = {
    "RETURN_TREND",
    "RISK_DRAWDOWN",
    "VALUATION_FUNDAMENTALS",
    "INCOME_DISTRIBUTIONS",
    "FUND_STRUCTURE",
    "DIVERSIFICATION_OVERLAP",
    "REGIME_PORTFOLIO_FIT",
}
HORIZONS = {"POINT_IN_TIME", "1M", "3M", "1Y", "3Y", "5Y"}
DIRECTIONS = {"HIGHER_IS_BETTER", "LOWER_IS_BETTER", "CONTEXT_DEPENDENT", "INFORMATIONAL"}
VALUE_TYPES = {"DECIMAL", "CURRENCY", "INTEGER", "BOOLEAN", "CATEGORY"}
METRIC_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class AnalyticsContractError(ValueError):
    """Raised when Phase 2 analytics contracts fail closed."""


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AnalyticsContractError(f"Expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalyticsContractError(message)


def validate_metric_definition(metric: dict[str, Any]) -> None:
    required = {
        "metric_id", "pillar", "value_type", "direction", "required_domains",
        "supported_horizons", "minimum_observations", "formula_version", "benchmark_required",
    }
    _require(set(metric) == required, f"Unexpected metric fields: {metric.get('metric_id')}")
    _require(bool(METRIC_ID_PATTERN.fullmatch(str(metric["metric_id"]))), "Invalid metric_id")
    _require(metric["pillar"] in PILLARS, "Unknown analytics pillar")
    _require(metric["value_type"] in VALUE_TYPES, "Unknown value type")
    _require(metric["direction"] in DIRECTIONS, "Unknown metric direction")
    domains = metric["required_domains"]
    _require(isinstance(domains, list) and domains and len(domains) == len(set(domains)), "Domains must be unique and nonempty")
    horizons = metric["supported_horizons"]
    _require(isinstance(horizons, list) and horizons and len(horizons) == len(set(horizons)), "Horizons must be unique and nonempty")
    _require(set(horizons).issubset(HORIZONS), "Unknown metric horizon")
    _require(isinstance(metric["minimum_observations"], int) and metric["minimum_observations"] >= 1, "Invalid observation floor")
    _require(bool(SEMVER_PATTERN.fullmatch(str(metric["formula_version"]))), "Invalid formula version")
    _require(isinstance(metric["benchmark_required"], bool), "benchmark_required must be boolean")


def validate_phase_2_1(root: Path) -> dict[str, Any]:
    lock = _load_object(root / "config/governance/phase_2_analytics_lock.json")
    catalog = _load_object(root / "config/analytics/metric_catalog.json")
    registry = _load_object(root / "config/contracts/contract_registry.json")

    _require(lock.get("phase") == "2" and lock.get("subphase") == "2.1", "Unexpected phase identity")
    _require(lock.get("fail_closed") is True, "Analytics governance must fail closed")
    _require(set(lock.get("required_etf_pillars", [])) == PILLARS, "All seven ETF pillars are required")
    _require(lock.get("primary_strategic_horizon") == "3Y", "3Y must remain the primary strategic horizon")
    _require(set(lock.get("required_horizons", [])) == {"1M", "3M", "1Y", "3Y", "5Y"}, "Required horizons drifted")

    controls = lock.get("required_calculation_controls", {})
    for key in (
        "point_in_time_only", "total_return_primary", "provider_adjusted_and_reconstructed_returns_reconciled",
        "metric_formula_version_required", "input_lineage_required", "observation_cutoff_required",
    ):
        _require(controls.get(key) is True, f"Required calculation control disabled: {key}")
    for key in ("look_ahead_allowed", "survivorship_bias_allowed", "silent_imputation_allowed", "missing_evidence_rewarded"):
        _require(controls.get(key) is False, f"Prohibited calculation behavior enabled: {key}")

    authority = lock.get("phase_2_1_authority", {})
    _require(authority.get("metric_contract_definition") is True, "Metric contract definition authority is required")
    for key, value in authority.items():
        if key not in {"metric_contract_definition", "analytics_architecture_definition"}:
            _require(value is False, f"Phase 2.1 authority expansion: {key}")

    metrics = catalog.get("metrics")
    _require(isinstance(metrics, list) and metrics, "Metric catalog must be nonempty")
    ids: list[str] = []
    pillars: set[str] = set()
    for metric in metrics:
        _require(isinstance(metric, dict), "Metric definitions must be objects")
        validate_metric_definition(metric)
        ids.append(metric["metric_id"])
        pillars.add(metric["pillar"])
    _require(len(ids) == len(set(ids)), "Duplicate metric_id")
    _require(pillars == PILLARS, "Metric catalog must cover all seven pillars")
    _require(catalog.get("primary_strategic_horizon") == "3Y", "Catalog strategic horizon drifted")

    contracts = {entry.get("contract_id"): entry for entry in registry.get("contracts", [])}
    entry = contracts.get("native.analytics_metric_definition")
    _require(isinstance(entry, dict), "Analytics metric contract is not registered")
    _require(entry.get("version") == "1.0.0" and entry.get("status") == "ACTIVE", "Analytics metric contract registration drifted")
    schema_path = root / str(entry.get("schema"))
    _require(schema_path.is_file(), "Analytics metric schema is missing")

    return {
        "phase": "2.1",
        "status": "PASS",
        "metric_count": len(metrics),
        "pillars": sorted(pillars),
        "primary_strategic_horizon": "3Y",
        "production_analytics_authorized": False,
        "scoring_authorized": False,
        "ranking_authorized": False,
        "recommendations_authorized": False,
        "automatic_execution_authorized": False,
    }
