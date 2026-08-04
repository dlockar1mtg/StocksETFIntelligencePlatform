from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Phase1IntegrationError(ValueError):
    """Raised when the integrated Phase 1 foundation violates governance."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise Phase1IntegrationError(f"Expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase1IntegrationError(message)


def validate_phase_1(root: Path) -> dict[str, Any]:
    completion = load_json(root / "config/certification/phase_1_completion.json")

    _require(completion.get("certification_id") == "stocks_etf_phase_1_data_foundation", "Unexpected certification identity")
    _require(completion.get("required_subphases") == ["1.1", "1.2", "1.3", "1.4", "1.5"], "Phase sequence is incomplete")
    _require(completion.get("minimum_tests_required", 0) >= 106, "Regression test floor is too low")
    _require(completion.get("fail_closed") is True, "Phase 1 must fail closed")
    _require(completion.get("critical_failures_block_certification") is True, "Critical failures must block certification")

    for relative in completion.get("required_control_files", []):
        _require((root / relative).is_file(), f"Missing required control file: {relative}")

    governance = load_json(root / "config/governance/phase_1_governance_lock.json")
    providers = load_json(root / "config/providers/provider_contracts.json")
    acquisition = load_json(root / "config/acquisition/raw_capture_policy.json")
    normalization = load_json(root / "config/normalization/normalization_policy.json")
    quality = load_json(root / "config/quality/evidence_quality_policy.json")
    security_master = load_json(root / "config/security/security_master.json")
    universe = load_json(root / "config/universe/etf_universe_policy.json")

    governed_ids = {item["security_id"] for item in security_master["securities"]}
    required_seed_ids = set(completion["required_security_ids"])
    governance_seed_ids = set(governance.get("seed_security_ids", []))
    policy_seed_ids = set(universe.get("seed_security_ids", []))

    _require(required_seed_ids == governance_seed_ids == policy_seed_ids, "Seed security identity drift detected")
    _require(required_seed_ids.issubset(governed_ids), "Required seed securities are missing from security master")
    _require(universe.get("seed_securities_must_remain_present") is True, "Seed securities must remain mandatory")
    _require(universe.get("universe_expansion_requires_certification") is True, "Universe expansion certification weakened")
    _require(universe.get("analytics_engine_must_not_hard_code_tickers") is True, "Ticker hard-coding protection weakened")
    _require(set(providers["governed_domains"]) == set(completion["required_governed_domains"]), "Governed data-domain drift detected")
    _require(set(quality["governed_domains"]) == set(completion["required_governed_domains"]), "Quality-domain drift detected")

    behaviors = governance.get("required_behaviors", {})
    _require(behaviors.get("missing_evidence_rewarded") is False, "Missing evidence cannot be rewarded")
    _require(behaviors.get("missing_evidence_silently_imputed") is False, "Silent imputation protection weakened")
    _require(behaviors.get("look_ahead_allowed") is False, "Look-ahead protection weakened")
    _require(behaviors.get("source_conflicts_preserved") is True, "Source conflicts must be preserved")
    _require(behaviors.get("conflicts_quarantined") is True, "Source conflicts must be quarantined")
    _require(behaviors.get("direct_uip_database_writes_allowed") is False, "Direct UIP writes must remain prohibited")

    _require(providers.get("conflicting_observations_must_be_preserved") is True, "Provider conflicts must be preserved")
    _require(providers.get("critical_conflicts_must_be_quarantined") is True, "Provider critical conflicts must be quarantined")
    _require(acquisition.get("raw_records_immutable") is True, "Raw captures must be immutable")
    _require(acquisition.get("raw_payloads_must_remain_outside_git") is True, "Raw payloads must remain outside Git")
    _require(acquisition.get("conflict_policy") == "QUARANTINE", "Acquisition conflicts must route to quarantine")
    _require(normalization.get("required_point_in_time_fields") == ["as_of_date", "effective_at_utc", "available_at_utc"], "Point-in-time normalization weakened")
    _require(normalization.get("silent_missing_value_imputation_forbidden") is True, "Normalization silent imputation protection weakened")
    _require(normalization.get("critical_conflicts_quarantined") is True, "Normalization conflict quarantine weakened")
    _require(normalization.get("provider_adjusted_reconciliation_required") is True, "Adjusted-price reconciliation weakened")
    _require(quality.get("missing_evidence_reduces_confidence") is True, "Quality confidence penalty weakened")
    _require(quality.get("blocked_evidence_cannot_be_promoted") is True, "Blocked evidence promotion protection weakened")
    _require(quality.get("unknown_freshness_requires_quarantine") is True, "Unknown freshness quarantine weakened")
    _require(quality.get("critical_conflicts_require_quarantine") is True, "Quality conflict quarantine weakened")

    for key in (
        "certified_market_monitoring_authorized",
        "certified_analytics_authorized",
        "certified_recommendations_authorized",
        "certified_uip_export_authorized",
        "automatic_execution_authorized",
        "direct_uip_database_writes_authorized",
    ):
        _require(completion.get(key) is False, f"Unauthorized authority expansion: {key}")

    return {
        "certification_id": completion["certification_id"],
        "status": "PASS",
        "required_subphases": completion["required_subphases"],
        "minimum_tests_required": completion["minimum_tests_required"],
        "seed_security_ids": sorted(required_seed_ids),
        "security_ids": sorted(governed_ids),
        "governed_domains": sorted(providers["governed_domains"]),
    }
