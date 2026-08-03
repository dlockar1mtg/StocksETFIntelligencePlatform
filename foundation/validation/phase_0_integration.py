from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Phase0IntegrationError(ValueError):
    """Raised when Phase 0 controls are incomplete or inconsistent."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase0IntegrationError(f"Unable to load governed JSON: {path}") from exc
    if not isinstance(document, dict):
        raise Phase0IntegrationError(f"Governed JSON must be an object: {path}")
    return document


def validate_completion_control(root: Path, control: dict[str, Any]) -> None:
    if control.get("phase") != "0":
        raise Phase0IntegrationError("Completion control must govern Phase 0")
    if control.get("required_subphases") != ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7"]:
        raise Phase0IntegrationError("Required subphase sequence is incomplete")
    if control.get("minimum_regression_tests", 0) < 56:
        raise Phase0IntegrationError("Minimum regression requirement is too low")
    for flag in (
        "fail_closed",
        "production_authority_granted",
        "automatic_execution_authorized",
        "direct_uip_database_writes_authorized",
        "individual_stock_production_authorized",
    ):
        expected = flag == "fail_closed"
        if control.get(flag) is not expected:
            raise Phase0IntegrationError(f"Invalid authority flag: {flag}")
    for relative_path in control.get("required_control_files", []):
        if not (root / relative_path).is_file():
            raise Phase0IntegrationError(f"Missing required control file: {relative_path}")


def validate_cross_control_consistency(root: Path, control: dict[str, Any]) -> None:
    security_master = load_json(root / "config/security/security_master.json")
    universe = load_json(root / "config/universe/etf_universe_policy.json")
    benchmark_registry = load_json(root / "config/security/benchmark_registry.json")
    market_calendar = load_json(root / "config/market/market_calendar.json")
    return_standard = load_json(root / "config/market/return_standard.json")
    source_authority = load_json(root / "config/sources/source_authority.json")
    data_zones = load_json(root / "config/data/data_zones.json")

    expected_ids = set(control["tier_1_security_ids"])
    master_ids = {item["security_id"] for item in security_master["securities"]}
    eligible_ids = set(universe["security_ids"])
    if expected_ids != master_ids or expected_ids != eligible_ids:
        raise Phase0IntegrationError("Tier 1 security identity is inconsistent across controls")

    benchmark_ids = {item["benchmark_id"] for item in benchmark_registry["benchmarks"]}
    for security in security_master["securities"]:
        if security["benchmark_id"] not in benchmark_ids:
            raise Phase0IntegrationError("Security references an unknown benchmark")

    if market_calendar.get("holiday_source_tier_required") != 1:
        raise Phase0IntegrationError("Market calendar must use Tier 1 authority")
    if (
        return_standard.get("security_return_basis") != "total_return"
        or return_standard.get("benchmark_return_basis") != "total_return"
        or return_standard.get("price_return_allowed_for_certified_comparison") is not False
        or return_standard.get("mixed_return_bases") != "BLOCK"
    ):
        raise Phase0IntegrationError("Return comparison must use total return")
    if not source_authority.get("unknown_sources_blocked"):
        raise Phase0IntegrationError("Unknown sources must remain blocked")
    if (
        not source_authority.get("source_conflicts_preserved")
        or not source_authority.get("silent_conflict_resolution_forbidden")
        or not data_zones.get("conflicted_records_must_be_quarantined")
    ):
        raise Phase0IntegrationError("Source conflicts must remain preserved")


def validate_phase_0(root: Path) -> dict[str, Any]:
    control = load_json(root / "config/certification/phase_0_completion.json")
    validate_completion_control(root, control)
    validate_cross_control_consistency(root, control)
    return control
