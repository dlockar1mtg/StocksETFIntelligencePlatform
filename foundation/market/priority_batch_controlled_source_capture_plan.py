from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_inputs(
    route_ledger: dict[str, Any],
    reliability_review: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    records = list(route_ledger.get("records", []))
    if len(records) != int(policy["required_route_population"]):
        raise ValueError("Priority route population drifted")

    security_ids = [record.get("security_id") for record in records]
    if len(set(security_ids)) != len(security_ids):
        raise ValueError("Duplicate priority-batch security identity")

    if route_ledger.get("selected_priority_rank") != policy["selected_priority_rank"]:
        raise ValueError("Priority rank drifted")
    if route_ledger.get("selected_issuer_key") != policy["selected_issuer_key"]:
        raise ValueError("Issuer key drifted")
    if route_ledger.get("selected_issuer_name") != policy["selected_issuer_name"]:
        raise ValueError("Issuer name drifted")
    if route_ledger.get("route_coverage_complete") is not True:
        raise ValueError("Route coverage is incomplete")
    if route_ledger.get("source_capture_executed") is not False:
        raise ValueError("Source capture was already executed")

    certified = list(reliability_review.get("certified_route_types", []))
    suspended = list(reliability_review.get("suspended_route_types", []))
    if certified != [policy["required_certified_route_type"]]:
        raise ValueError("Exactly one required certified route is not present")
    if policy["required_suspended_route_type"] not in suspended:
        raise ValueError("Failed issuer route is not suspended")
    if reliability_review.get("controlled_batch_capture_plan_authorized") is not True:
        raise ValueError("Controlled capture-plan preparation is not authorized")
    if reliability_review.get("priority_batch_source_capture_authorized") is not False:
        raise ValueError("Capture execution was prematurely authorized")

    for record in records:
        for field in (
            "security_id",
            "symbol",
            "sec_cik",
            "sec_series_id",
            "sec_class_contract_id",
        ):
            if not record.get(field):
                raise ValueError(f"Missing required route field: {field}")
        if record.get("route_state") != "ROUTE_CANDIDATE_READY":
            raise ValueError("A priority-batch route record is not ready")
        routes = list(record.get("candidate_routes", []))
        selected = [
            route
            for route in routes
            if route.get("route_type") == policy["required_certified_route_type"]
        ]
        if len(selected) != 1:
            raise ValueError("Certified SEC route is missing or duplicated")
        if selected[0].get("official_domain") != "sec.gov":
            raise ValueError("Certified SEC route domain drifted")
        if selected[0].get("capture_authorized") is not False:
            raise ValueError("Route already has capture authority")


def build_capture_plan(
    route_ledger: dict[str, Any],
    reliability_review: dict[str, Any],
    policy: dict[str, Any],
    operating_date: str,
) -> dict[str, Any]:
    validate_inputs(route_ledger, reliability_review, policy)

    records = sorted(
        deepcopy(route_ledger["records"]),
        key=lambda record: (
            str(record["sec_series_id"]),
            str(record["sec_class_contract_id"]),
            str(record["security_id"]),
        ),
    )

    plan_records: list[dict[str, Any]] = []
    template = policy["execution"]["sec_search_template"]
    raw_template = policy["execution"]["raw_path_template"]

    for sequence, record in enumerate(records, start=1):
        request_url = template.format(
            cik=record["sec_cik"],
            series_id=record["sec_series_id"],
            class_contract_id=record["sec_class_contract_id"],
        )
        raw_path = raw_template.format(
            operating_date=operating_date,
            security_id=record["security_id"],
        )
        plan_records.append(
            {
                "sequence": sequence,
                "security_id": record["security_id"],
                "symbol": record["symbol"],
                "issuer_key": record["issuer_key"],
                "sec_cik": record["sec_cik"],
                "sec_series_id": record["sec_series_id"],
                "sec_class_contract_id": record["sec_class_contract_id"],
                "route_type": policy["required_certified_route_type"],
                "source_tier": "SEC_FILING",
                "official_domain": "sec.gov",
                "request_url": request_url,
                "expected_identity_markers": [
                    record["sec_series_id"],
                    record["sec_class_contract_id"],
                    record["symbol"],
                ],
                "raw_path": raw_path,
                "capture_state": "CAPTURE_PENDING",
                "attempt_count": 0,
                "http_status": None,
                "final_url": None,
                "redirect_chain": [],
                "retrieved_at_utc": None,
                "payload_sha256": None,
                "failure_reason": None,
                "identity_markers_evaluated": False,
                "identity_confirmed": False,
                "capture_authorized": False,
                "taxonomy_dimensions_assigned": False,
                "taxonomy_classification_authorized": False,
                "production_taxonomy_authority": False,
            }
        )

    authority = deepcopy(policy["authority"])
    return {
        "phase": "3.6b.3k",
        "policy_version": policy["policy_version"],
        "operating_date": operating_date,
        "selected_priority_rank": policy["selected_priority_rank"],
        "selected_issuer_key": policy["selected_issuer_key"],
        "selected_issuer_name": policy["selected_issuer_name"],
        "certified_route_type": policy["required_certified_route_type"],
        "suspended_route_type": policy["required_suspended_route_type"],
        "required_record_count": policy["required_route_population"],
        "plan_record_count": len(plan_records),
        "capture_plan_complete": len(plan_records) == policy["required_route_population"],
        "capture_execution_performed": False,
        "execution_contract": deepcopy(policy["execution"]),
        "completion_criteria": deepcopy(policy["completion_criteria"]),
        "capture_state_counts": {"CAPTURE_PENDING": len(plan_records)},
        "authority": authority,
        "next_required_step": "PRIORITY_BATCH_CONTROLLED_SOURCE_CAPTURE_PLAN_CERTIFICATION",
        "records": plan_records,
    }


def write_outputs(plan: dict[str, Any], output_path: Path, summary_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    digest = _sha256(output_path.read_bytes())
    summary = {
        "phase": "3.6b.3k",
        "required_record_count": plan["required_record_count"],
        "plan_record_count": plan["plan_record_count"],
        "capture_state_counts": plan["capture_state_counts"],
        "capture_plan_complete": plan["capture_plan_complete"],
        "capture_execution_performed": plan["capture_execution_performed"],
        "certified_route_type": plan["certified_route_type"],
        "suspended_route_type": plan["suspended_route_type"],
        "next_required_step": plan["next_required_step"],
        "capture_plan_sha256": digest,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
