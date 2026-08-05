from __future__ import annotations

import hashlib
import json
import urllib.parse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host_allowed(url: str, required_domain: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host == required_domain or host.endswith("." + required_domain)


def validate_capture_plan(plan: dict[str, Any], policy: dict[str, Any], plan_bytes: bytes) -> None:
    if plan.get("phase") != policy["required_input_phase"]:
        raise ValueError("Unexpected capture-plan phase")
    if _sha256(plan_bytes) != policy["required_capture_plan_sha256"]:
        raise ValueError("Capture-plan SHA-256 mismatch")
    records = list(plan.get("records", []))
    expected_count = int(policy["required_record_count"])
    if int(plan.get("required_record_count", -1)) != expected_count:
        raise ValueError("Required record count drifted")
    if int(plan.get("plan_record_count", -1)) != expected_count or len(records) != expected_count:
        raise ValueError("Capture-plan population drifted")
    if plan.get("capture_plan_complete") is not True:
        raise ValueError("Capture plan is incomplete")
    if plan.get("capture_execution_performed") is not False:
        raise ValueError("Capture was already executed")
    if plan.get("certified_route_type") != policy["required_certified_route_type"]:
        raise ValueError("Certified route drifted")
    if plan.get("suspended_route_type") != policy["required_suspended_route_type"]:
        raise ValueError("Suspended route drifted")

    contract = plan.get("execution_contract", {})
    required_contract = policy["execution_contract"]
    for key in (
        "ordering",
        "maximum_requests_per_second",
        "maximum_retry_attempts",
        "request_timeout_seconds",
        "checkpoint_after_each_record",
        "resume_safe",
        "immutable_raw_storage",
    ):
        if contract.get(key) != required_contract[key]:
            raise ValueError(f"Execution contract drifted: {key}")

    ids: list[str] = []
    raw_paths: list[str] = []
    expected_sequence = 1
    for record in records:
        security_id = record.get("security_id")
        if not security_id:
            raise ValueError("Missing stable security identity")
        ids.append(str(security_id))
        if int(record.get("sequence", -1)) != expected_sequence:
            raise ValueError("Capture-plan sequence is not contiguous")
        expected_sequence += 1
        if record.get("capture_state") != policy["required_input_state"]:
            raise ValueError("Capture record is not pending")
        if int(record.get("attempt_count", -1)) != 0:
            raise ValueError("Capture record has premature attempts")
        if record.get("route_type") != policy["required_certified_route_type"]:
            raise ValueError("Uncertified route present")
        if record.get("official_domain") != required_contract["official_domain"]:
            raise ValueError("Official domain drifted")
        request_url = str(record.get("request_url") or "")
        if not request_url.startswith("https://") or not _host_allowed(request_url, required_contract["official_domain"]):
            raise ValueError("Request URL violates official HTTPS-domain policy")
        for field in ("sec_cik", "sec_series_id", "sec_class_contract_id", "symbol"):
            if not record.get(field):
                raise ValueError(f"Missing required identity marker: {field}")
        markers = list(record.get("expected_identity_markers", []))
        if len(markers) != 3 or len(set(markers)) != 3:
            raise ValueError("Expected identity markers are incomplete or duplicated")
        raw_path = str(record.get("raw_path") or "")
        if not raw_path.startswith(required_contract["raw_path_prefix"]):
            raise ValueError("Immutable raw path violates certified prefix")
        if str(security_id) not in raw_path:
            raise ValueError("Immutable raw path lacks security identity")
        raw_paths.append(raw_path)
        for evidence_field in (
            "http_status",
            "final_url",
            "retrieved_at_utc",
            "payload_sha256",
            "failure_reason",
        ):
            if record.get(evidence_field) is not None:
                raise ValueError("Premature capture evidence present")
        if list(record.get("redirect_chain", [])):
            raise ValueError("Premature redirect evidence present")
        if record.get("capture_authorized") is not False:
            raise ValueError("Record-level capture authority must remain false before execution")
        if record.get("taxonomy_dimensions_assigned") is not False:
            raise ValueError("Taxonomy dimensions were assigned prematurely")
        if record.get("taxonomy_classification_authorized") is not False:
            raise ValueError("Taxonomy classification was authorized prematurely")
        if record.get("production_taxonomy_authority") is not False:
            raise ValueError("Production taxonomy authority was granted prematurely")

    if len(set(ids)) != expected_count:
        raise ValueError("Duplicate or missing security identities")
    if len(set(raw_paths)) != expected_count:
        raise ValueError("Duplicate immutable raw paths")


def build_authorization(plan: dict[str, Any], policy: dict[str, Any], plan_bytes: bytes) -> dict[str, Any]:
    validate_capture_plan(plan, policy, plan_bytes)
    authorization = {
        "phase": "3.6b.3l",
        "policy_version": policy["policy_version"],
        "authorized_at_utc": _utc_now(),
        "capture_plan_phase": plan["phase"],
        "capture_plan_sha256": _sha256(plan_bytes),
        "authorized_record_count": len(plan["records"]),
        "authorized_route_type": plan["certified_route_type"],
        "suspended_route_type": plan["suspended_route_type"],
        "execution_contract": deepcopy(policy["execution_contract"]),
        "authority": deepcopy(policy["authority"]),
        "capture_execution_authorized": True,
        "automatic_execution_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "authorization_complete": True,
        "next_required_step": "PRIORITY_BATCH_CONTROLLED_SOURCE_CAPTURE_EXECUTION",
        "critical_failures": [],
    }
    return authorization


def write_authorization(
    plan_path: Path,
    policy_path: Path,
    output_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes.decode("utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    authorization = build_authorization(plan, policy, plan_bytes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(authorization, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "phase": "3.6b.3l",
        "authorization_complete": True,
        "authorized_record_count": authorization["authorized_record_count"],
        "authorized_route_type": authorization["authorized_route_type"],
        "capture_execution_authorized": True,
        "automatic_execution_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": authorization["next_required_step"],
        "capture_plan_sha256": authorization["capture_plan_sha256"],
        "authorization_sha256": _sha256(output_path.read_bytes()),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return authorization, summary
