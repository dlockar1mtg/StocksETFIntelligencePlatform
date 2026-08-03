from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class Phase167IntegrationError(ValueError):
    """Raised when final Phase 1 dynamic-universe controls fail closed."""


def _load_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Phase167IntegrationError(f"Required certification evidence missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise Phase167IntegrationError(f"Expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase167IntegrationError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_attestation(control: dict[str, Any], attestation: dict[str, Any]) -> None:
    _require(attestation.get("attestation_version") == "1.0.0", "Unexpected snapshot attestation version")
    _require(attestation.get("snapshot_id") == control["snapshot_id"], "Attested snapshot identity drift detected")
    _require(attestation.get("snapshot_status") == "COMPLETE", "Attested snapshot is not complete")
    _require(attestation.get("operating_date") == control["operating_date"], "Attested operating date drift detected")
    _require(attestation.get("operating_timezone") == control["operating_timezone"], "Attested operating timezone drift detected")
    _require(attestation.get("snapshot_sha256") == control["snapshot_sha256"], "Attested snapshot hash drift detected")
    _require(attestation.get("counts") == control["expected_counts"], "Attested snapshot counts drift detected")
    _require(sorted(attestation.get("blocked_symbols", [])) == sorted(control["expected_blocked_symbols"]), "Attested blocked-symbol set drift detected")
    _require(set(attestation.get("required_seed_security_ids", [])) == set(control["required_seed_security_ids"]), "Attested seed security identity drift detected")
    _require(set(attestation.get("required_seed_symbols", [])) == set(control["required_seed_symbols"]), "Attested seed symbol drift detected")
    _require(attestation.get("structural_baseline_replaced") is True, "Structural baseline replacement is not attested")
    _require(attestation.get("taxonomy_pending") is True, "Pending taxonomy state is not attested")
    _require(attestation.get("analytics_eligibility_implied") is False, "Attestation improperly implies analytics eligibility")
    _require(attestation.get("generated_snapshot_committed_to_git") is False, "Generated snapshot must remain outside Git")
    for key in (
        "recommendation_authority",
        "analytics_authority",
        "portfolio_authority",
        "execution_authority",
        "direct_uip_database_write_authority",
    ):
        _require(attestation.get(key) is False, f"Snapshot attestation authority expansion: {key}")


def _validate_local_snapshot(control: dict[str, Any], snapshot_path: Path) -> None:
    _require(_sha256(snapshot_path) == control["snapshot_sha256"], "Certified snapshot hash drift detected")
    snapshot = _load_object(snapshot_path)
    _require(snapshot.get("snapshot_id") == control["snapshot_id"], "Snapshot identity drift detected")
    _require(snapshot.get("snapshot_status") == "COMPLETE", "Snapshot is not complete")
    _require(snapshot.get("operating_date") == control["operating_date"], "Operating date drift detected")
    _require(snapshot.get("operating_timezone") == control["operating_timezone"], "Operating timezone drift detected")
    _require(snapshot.get("counts") == control["expected_counts"], "Snapshot counts drift detected")

    records = snapshot.get("records")
    _require(isinstance(records, list), "Snapshot records must be an array")
    _require(len(records) == control["expected_counts"]["total_records"], "Snapshot record count mismatch")
    _require(len(records) > control["structural_baseline_record_count"], "Full snapshot did not replace structural baseline")

    security_ids = [record.get("security_id") for record in records]
    symbols = [record.get("symbol") for record in records]
    _require(len(security_ids) == len(set(security_ids)), "Duplicate stable security identity")
    _require(len(symbols) == len(set(symbols)), "Duplicate symbol identity")
    _require(set(control["required_seed_security_ids"]).issubset(set(security_ids)), "Seed security identity missing")
    _require(set(control["required_seed_symbols"]).issubset(set(symbols)), "Seed symbol missing")

    blocked = {record.get("symbol") for record in records if record.get("final_state") == "BLOCKED"}
    _require(blocked == set(control["expected_blocked_symbols"]), "Blocked-symbol set drift detected")
    for record in records:
        broker_status = record.get("broker_status")
        final_state = record.get("final_state")
        if broker_status == "ELIGIBLE":
            _require(final_state == "BROKER_ELIGIBLE", f"{record.get('symbol')}: eligible record not broker eligible")
            _require(bool(record.get("robinhood_instrument_id")), f"{record.get('symbol')}: eligible record lacks instrument identity")
        else:
            _require(final_state == "BLOCKED", f"{record.get('symbol')}: noneligible record improperly promoted")
        _require(record.get("taxonomy_status") == "PENDING", f"{record.get('symbol')}: taxonomy authority improperly granted")
        _require(record.get("analytics_status") == "BLOCKED", f"{record.get('symbol')}: analytics authority improperly granted")

    snapshot_authority = snapshot.get("attestation", {})
    for key in (
        "recommendation_authority",
        "analytics_authority",
        "portfolio_authority",
        "execution_authority",
        "direct_uip_database_write_authority",
    ):
        _require(snapshot_authority.get(key) is False, f"Snapshot authority expansion: {key}")


def validate_phase_1_6_7(root: Path) -> dict[str, Any]:
    control = _load_object(root / "config/certification/phase_1_6_7_completion.json")
    _require(control.get("certification_id") == "stocks_etf_phase_1_dynamic_universe", "Unexpected certification identity")
    _require(control.get("phase") == "1.6.7", "Unexpected certification phase")
    _require(control.get("fail_closed") is True, "Certification must fail closed")
    _require(control.get("critical_failures_block_certification") is True, "Critical failures must block certification")
    _require(control.get("minimum_tests_required", 0) >= 209, "Regression floor is too low")

    expected_subphases = ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6.1", "1.6.2", "1.6.3", "1.6.4", "1.6.5", "1.6.6", "1.6.6a", "1.6.6b", "1.6.6c", "1.6.7"]
    _require(control.get("required_subphases") == expected_subphases, "Integrated Phase 1 sequence is incomplete")
    _require(control.get("generated_snapshot_must_remain_outside_git") is True, "Generated snapshot Git boundary weakened")
    _require(control.get("ci_may_validate_signed_attestation_without_generated_snapshot") is True, "CI attestation mode not authorized")
    _require(control.get("local_snapshot_if_present_must_match_attestation") is True, "Local snapshot reconciliation weakened")

    attestation_path = root / str(control["snapshot_attestation_relative_path"])
    attestation = _load_object(attestation_path)
    _validate_attestation(control, attestation)

    snapshot_path = root / str(control["snapshot_relative_path"])
    evidence_mode = "ATTESTATION_ONLY"
    if snapshot_path.is_file():
        _validate_local_snapshot(control, snapshot_path)
        evidence_mode = "LOCAL_SNAPSHOT_VERIFIED"

    for key in (
        "certified_market_monitoring_authorized",
        "certified_analytics_authorized",
        "certified_recommendations_authorized",
        "certified_portfolio_authorized",
        "certified_uip_export_authorized",
        "automatic_execution_authorized",
        "direct_uip_database_writes_authorized",
    ):
        _require(control.get(key) is False, f"Certification authority expansion: {key}")

    return {
        "certification_id": control["certification_id"],
        "status": "PASS",
        "snapshot_id": attestation["snapshot_id"],
        "snapshot_sha256": attestation["snapshot_sha256"],
        "counts": attestation["counts"],
        "blocked_symbols": sorted(attestation["blocked_symbols"]),
        "required_subphases": control["required_subphases"],
        "snapshot_evidence_mode": evidence_mode,
    }
