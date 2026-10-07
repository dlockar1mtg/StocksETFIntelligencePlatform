from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _official_https(url: str, allowed_domains: set[str]) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == d or host.endswith("." + d) for d in allowed_domains)


def validate_inputs(execution: dict[str, Any], policy: dict[str, Any]) -> None:
    records = list(execution.get("records", []))
    if len(records) != int(policy["required_pilot_record_count"]):
        raise ValueError("Pilot record count drifted")
    security_ids = [record.get("security_id") for record in records]
    if len(security_ids) != len(set(security_ids)):
        raise ValueError("Duplicate pilot security identity")
    request_count = sum(len(record.get("discovery_requests", [])) for record in records)
    if request_count != int(policy["required_request_count"]):
        raise ValueError("Discovery request count drifted")
    expected_routes = set(policy["required_route_types"])
    observed_routes: set[str] = set()
    for record in records:
        if record.get("source_capture_authorized") is not False:
            raise ValueError("Premature record capture authority")
        for request in record.get("discovery_requests", []):
            observed_routes.add(str(request.get("route_type")))
            if request.get("capture_authorized") is not False:
                raise ValueError("Premature request capture authority")
            if not request.get("payload_sha256") or not request.get("retrieved_at_utc") or not request.get("raw_path"):
                raise ValueError("Discovery evidence lineage is incomplete")
    if observed_routes != expected_routes:
        raise ValueError("Required route set drifted")


def review_routes(execution: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validate_inputs(execution, policy)
    thresholds = policy["route_promotion_thresholds"]
    allowed_domains = {"sec.gov", "ishares.com", "blackrock.com"}
    grouped: dict[str, list[dict[str, Any]]] = {route: [] for route in policy["required_route_types"]}
    for record in execution["records"]:
        for request in record["discovery_requests"]:
            grouped[request["route_type"]].append(request)

    route_reviews: list[dict[str, Any]] = []
    for route_type in policy["required_route_types"]:
        requests = grouped[route_type]
        total = len(requests)
        resolved = sum(r.get("discovery_state") == "PRODUCT_SPECIFIC_RESOLVED" for r in requests)
        generic = sum(r.get("discovery_state") == "GENERIC_LANDING_PAGE" for r in requests)
        unresolved = sum(r.get("discovery_state") == "DISCOVERY_UNRESOLVED" for r in requests)
        conflicted = sum(r.get("discovery_state") == "DISCOVERY_CONFLICTED" for r in requests)
        quarantined = sum(r.get("discovery_state") == "DISCOVERY_QUARANTINED" for r in requests)
        lineage_complete = sum(
            bool(r.get("payload_sha256") and r.get("retrieved_at_utc") and r.get("raw_path")) for r in requests
        )
        official_urls = sum(_official_https(str(r.get("final_url") or ""), allowed_domains) for r in requests)
        success_rate = resolved / total if total else 0.0
        adverse_rate = (conflicted + quarantined) / total if total else 1.0
        lineage_rate = lineage_complete / total if total else 0.0
        official_url_rate = official_urls / total if total else 0.0

        qualifies = (
            total >= int(thresholds["minimum_sample_count"])
            and success_rate >= float(thresholds["minimum_product_specific_success_rate"])
            and adverse_rate <= float(thresholds["maximum_quarantined_or_conflicted_rate"])
            and lineage_rate >= float(thresholds["raw_evidence_coverage_required"])
            and official_url_rate == 1.0
        )
        if qualifies:
            decision = "CERTIFIED_FOR_CONTROLLED_BATCH_CAPTURE"
            reason = "PRODUCT_SPECIFIC_SUCCESS_AND_LINEAGE_THRESHOLDS_MET"
        elif total < int(thresholds["minimum_sample_count"]):
            decision = "INSUFFICIENT_EVIDENCE"
            reason = "MINIMUM_SAMPLE_NOT_MET"
        elif resolved == 0 and unresolved == total:
            decision = "SUSPENDED"
            reason = "ZERO_PRODUCT_SPECIFIC_RESOLUTION"
        else:
            decision = "REJECTED"
            reason = "PROMOTION_THRESHOLDS_NOT_MET"

        route_reviews.append({
            "route_type": route_type,
            "sample_count": total,
            "product_specific_resolved_count": resolved,
            "generic_landing_page_count": generic,
            "unresolved_count": unresolved,
            "conflicted_count": conflicted,
            "quarantined_count": quarantined,
            "product_specific_success_rate": success_rate,
            "adverse_state_rate": adverse_rate,
            "lineage_coverage_rate": lineage_rate,
            "official_https_url_rate": official_url_rate,
            "decision": decision,
            "decision_reason": reason,
            "capture_authorized": False,
        })

    certified = [r for r in route_reviews if r["decision"] == "CERTIFIED_FOR_CONTROLLED_BATCH_CAPTURE"]
    suspended = [r for r in route_reviews if r["decision"] == "SUSPENDED"]
    return {
        "phase": "3.6b.3j",
        "policy_version": policy["policy_version"],
        "pilot_record_count": len(execution["records"]),
        "request_count": sum(len(r["discovery_requests"]) for r in execution["records"]),
        "route_reviews": route_reviews,
        "certified_route_count": len(certified),
        "suspended_route_count": len(suspended),
        "certified_route_types": [r["route_type"] for r in certified],
        "suspended_route_types": [r["route_type"] for r in suspended],
        "controlled_batch_capture_plan_authorized": len(certified) == 1,
        "priority_batch_source_capture_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "authority": policy["authority"],
        "next_required_step": "PRIORITY_BATCH_CONTROLLED_SOURCE_CAPTURE_PLAN",
    }


def build_summary(review: dict[str, Any], output_path: Path) -> dict[str, Any]:
    return {
        "phase": review["phase"],
        "pilot_record_count": review["pilot_record_count"],
        "request_count": review["request_count"],
        "certified_route_count": review["certified_route_count"],
        "suspended_route_count": review["suspended_route_count"],
        "certified_route_types": review["certified_route_types"],
        "suspended_route_types": review["suspended_route_types"],
        "controlled_batch_capture_plan_authorized": review["controlled_batch_capture_plan_authorized"],
        "priority_batch_source_capture_authorized": False,
        "next_required_step": review["next_required_step"],
        "review_ledger_sha256": _sha256(output_path.read_bytes()),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
