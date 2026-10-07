from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class PriorityBatchRouteDiscoveryPilotError(ValueError):
    """Raised when Phase 3.6b.3h pilot construction fails closed."""


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise PriorityBatchRouteDiscoveryPilotError("RECORD_ARRAY_MISSING")


def _quantile_indexes(population_count: int, sample_count: int) -> list[int]:
    if population_count < sample_count or sample_count < 2:
        raise PriorityBatchRouteDiscoveryPilotError("INVALID_SAMPLE_GEOMETRY")
    return [round(index * (population_count - 1) / (sample_count - 1)) for index in range(sample_count)]


def build_route_discovery_pilot(route_ledger: Any, policy: dict[str, Any]) -> dict[str, Any]:
    records = _records(route_ledger)
    required = int(policy["required_route_population"])
    sample_count = int(policy["pilot_sample_count"])

    if len(records) != required:
        raise PriorityBatchRouteDiscoveryPilotError("ROUTE_POPULATION_COUNT_MISMATCH")

    identities = [record.get("security_id") for record in records]
    if None in identities or len(set(identities)) != required:
        raise PriorityBatchRouteDiscoveryPilotError("DUPLICATE_OR_MISSING_SECURITY_ID")

    if route_ledger.get("route_coverage_complete") is not True:
        raise PriorityBatchRouteDiscoveryPilotError("ROUTE_COVERAGE_NOT_COMPLETE")

    ordered = sorted(records, key=lambda item: str(item["security_id"]))
    selected = [ordered[index] for index in _quantile_indexes(required, sample_count)]
    pilot_records: list[dict[str, Any]] = []

    for source in selected:
        if source.get("route_state") != policy["required_route_state"]:
            raise PriorityBatchRouteDiscoveryPilotError("PILOT_ROUTE_NOT_READY")

        routes = source.get("candidate_routes")
        if not isinstance(routes, list) or len(routes) != 2:
            raise PriorityBatchRouteDiscoveryPilotError("EXACTLY_TWO_CANDIDATE_ROUTES_REQUIRED")

        route_types = {route.get("route_type") for route in routes}
        if route_types != set(policy["allowed_route_types"]):
            raise PriorityBatchRouteDiscoveryPilotError("ROUTE_TYPE_CONTRACT_MISMATCH")

        requests: list[dict[str, Any]] = []
        for route in sorted(routes, key=lambda item: str(item.get("route_type"))):
            if route.get("capture_authorized") is not False:
                raise PriorityBatchRouteDiscoveryPilotError("PREMATURE_CAPTURE_AUTHORITY")
            if route.get("route_resolution_required") is not True:
                raise PriorityBatchRouteDiscoveryPilotError("ROUTE_ALREADY_TREATED_AS_RESOLVED")
            requests.append(
                {
                    "route_type": route.get("route_type"),
                    "source_tier": route.get("source_tier"),
                    "official_domain": route.get("official_domain"),
                    "identity_markers": route.get("identity_markers"),
                    "discovery_state": "DISCOVERY_PENDING",
                    "resolved_url": None,
                    "final_url": None,
                    "redirect_chain": [],
                    "http_status": None,
                    "retrieved_at_utc": None,
                    "payload_sha256": None,
                    "raw_path": None,
                    "failure_reason": None,
                    "capture_authorized": False,
                }
            )

        pilot_records.append(
            {
                "security_id": source["security_id"],
                "symbol": source.get("symbol"),
                "sec_cik": source.get("sec_cik"),
                "sec_series_id": source.get("sec_series_id"),
                "sec_class_contract_id": source.get("sec_class_contract_id"),
                "pilot_state": "DISCOVERY_PENDING",
                "discovery_requests": requests,
                "source_capture_authorized": False,
                "taxonomy_dimensions_assigned": False,
                "taxonomy_classification_authorized": False,
                "production_taxonomy_authority": False,
            }
        )

    state_counts = Counter(record["pilot_state"] for record in pilot_records)
    return {
        "phase": "3.6b.3h",
        "required_route_population": required,
        "pilot_sample_count": sample_count,
        "selection_method": policy["selection_method"],
        "selected_priority_rank": policy["selected_priority_rank"],
        "selected_issuer_key": policy["selected_issuer_key"],
        "selected_issuer_name": policy["selected_issuer_name"],
        "pilot_record_count": len(pilot_records),
        "pilot_state_counts": dict(sorted(state_counts.items())),
        "discovery_execution_performed": False,
        "pilot_manifest_complete": len(pilot_records) == sample_count,
        "next_required_step": "PRIORITY_BATCH_ROUTE_DISCOVERY_PILOT_EXECUTION",
        "records": pilot_records,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_payload = {key: value for key, value in result.items() if key != "records"}
    summary_payload["pilot_manifest_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary_payload["selected_securities"] = [
        {"security_id": record["security_id"], "symbol": record.get("symbol")}
        for record in result["records"]
    ]
    summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
