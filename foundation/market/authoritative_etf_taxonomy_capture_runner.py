from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any


class AuthoritativeTaxonomyCaptureRunnerError(ValueError):
    """Raised when capture orchestration violates governed controls."""


EXPECTED_POPULATION = 1077
EXPECTED_GROUP_COUNT = 103
EXPECTED_STANDARD_GROUPS = 102
EXPECTED_REMEDIATION_GROUPS = 1
EXPECTED_STANDARD_ETFS = 862
EXPECTED_REMEDIATION_ETFS = 215


def _validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("required_record_count") != EXPECTED_POPULATION:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Acquisition policy population must equal 1,077."
        )

    authority = policy.get("authority")

    if not isinstance(authority, dict):
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Acquisition authority block is required."
        )

    if authority.get("authoritative_evidence_manifest_build") is not True:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Execution-manifest construction is not authorized."
        )

    if authority.get("production_taxonomy_classification") is not False:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Runner must not expand classification authority."
        )


def _validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    summary = plan.get("summary")
    groups = plan.get("capture_groups")

    if not isinstance(summary, dict):
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Capture-plan summary is required."
        )

    if not isinstance(groups, list):
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Capture groups are required."
        )

    required_summary = {
        "governed_population": EXPECTED_POPULATION,
        "registrant_group_count": EXPECTED_GROUP_COUNT,
        "standard_registrant_count": EXPECTED_STANDARD_GROUPS,
        "standard_etf_count": EXPECTED_STANDARD_ETFS,
        "remediation_registrant_count": EXPECTED_REMEDIATION_GROUPS,
        "remediation_etf_count": EXPECTED_REMEDIATION_ETFS,
        "mixed_registrant_count": 0,
        "structural_identity_complete_population": EXPECTED_POPULATION,
        "structural_identity_conflict_population": 0,
    }

    for field, expected in required_summary.items():
        if summary.get(field) != expected:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Capture-plan summary drift: {field}."
            )

    if len(groups) != EXPECTED_GROUP_COUNT:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Capture plan must contain exactly 103 registrant groups."
        )

    seen_group_ids: set[str] = set()
    seen_security_ids: set[str] = set()

    standard_groups = 0
    remediation_groups = 0
    standard_etfs = 0
    remediation_etfs = 0

    for group in groups:
        group_id = group.get("capture_group_id")
        cik = group.get("sec_cik")
        lane = group.get("lane")
        security_ids = group.get("security_ids")

        if not group_id or not cik:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                "Capture group requires group ID and CIK."
            )

        if group_id in seen_group_ids:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Duplicate capture group: {group_id}"
            )

        seen_group_ids.add(group_id)

        if not isinstance(security_ids, list) or not security_ids:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Capture group {group_id} has no security membership."
            )

        if len(security_ids) != group.get("etf_count"):
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Capture group population mismatch: {group_id}"
            )

        for security_id in security_ids:
            if security_id in seen_security_ids:
                raise AuthoritativeTaxonomyCaptureRunnerError(
                    f"Duplicate security membership: {security_id}"
                )
            seen_security_ids.add(security_id)

        if lane == "STANDARD_REGISTRANT_AUTHORITY_ACQUISITION":
            if group.get("priority_remediation_etf_count") != 0:
                raise AuthoritativeTaxonomyCaptureRunnerError(
                    "Standard group contains remediation ETFs."
                )

            standard_groups += 1
            standard_etfs += len(security_ids)

        elif lane == "GOVERNED_EXISTING_REMEDIATION_ROUTE":
            if group.get("priority_remediation_etf_count") != len(security_ids):
                raise AuthoritativeTaxonomyCaptureRunnerError(
                    "Remediation group is not fully remediation-scoped."
                )

            remediation_groups += 1
            remediation_etfs += len(security_ids)

        else:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Unknown capture lane: {lane}"
            )

        if group.get("known_structural_identity_complete") is not True:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Incomplete structural identity: {group_id}"
            )

        if group.get("structural_identity_conflict") is not False:
            raise AuthoritativeTaxonomyCaptureRunnerError(
                f"Structural identity conflict: {group_id}"
            )

    if len(seen_security_ids) != EXPECTED_POPULATION:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Capture plan does not preserve all 1,077 security identities."
        )

    if standard_groups != EXPECTED_STANDARD_GROUPS:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Standard registrant count drift."
        )

    if remediation_groups != EXPECTED_REMEDIATION_GROUPS:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Remediation registrant count drift."
        )

    if standard_etfs != EXPECTED_STANDARD_ETFS:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Standard ETF count drift."
        )

    if remediation_etfs != EXPECTED_REMEDIATION_ETFS:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Remediation ETF count drift."
        )

    return groups


def build_execution_manifest(
    plan: dict[str, Any],
    policy: dict[str, Any],
    *,
    live_network_requested: bool = False,
) -> dict[str, Any]:
    """
    Build the deterministic execution contract.

    This function never performs network I/O.

    A future network executor may consume this manifest only after
    authoritative_source_capture is explicitly authorized.
    """
    _validate_policy(policy)
    groups = _validate_plan(plan)

    authority = policy["authority"]
    live_authorized = (
        authority.get("authoritative_source_capture") is True
    )

    if live_network_requested and not live_authorized:
        raise AuthoritativeTaxonomyCaptureRunnerError(
            "Live authoritative-source capture is not authorized."
        )

    execution_groups = []

    lane_counts = Counter()
    etf_lane_counts = Counter()

    for group in sorted(
        groups,
        key=lambda record: int(record["execution_order"]),
    ):
        lane = group["lane"]
        security_ids = list(group["security_ids"])

        lane_counts[lane] += 1
        etf_lane_counts[lane] += len(security_ids)

        if lane == "GOVERNED_EXISTING_REMEDIATION_ROUTE":
            execution_state = "PRESERVED_REMEDIATION_ROUTE"
            executor = "EXISTING_SERIES_CLASS_REMEDIATION_ARCHITECTURE"

        else:
            execution_state = "READY_FOR_AUTHORIZED_CAPTURE"
            executor = "STANDARD_REGISTRANT_CAPTURE"

        execution_groups.append(
            {
                "capture_group_id": group["capture_group_id"],
                "execution_order": group["execution_order"],
                "sec_cik": group["sec_cik"],
                "lane": lane,
                "routing_tier": group["routing_tier"],
                "etf_count": group["etf_count"],
                "security_ids": security_ids,
                "symbols": list(group.get("symbols", [])),
                "source_route_priority": deepcopy(
                    group["source_route_priority"]
                ),
                "executor": executor,
                "execution_state": execution_state,
                "live_capture_authorized": live_authorized,
                "network_requests_performed": 0,
            }
        )

    summary = {
        "governed_population": EXPECTED_POPULATION,
        "registrant_group_count": EXPECTED_GROUP_COUNT,
        "standard_registrant_count": EXPECTED_STANDARD_GROUPS,
        "standard_etf_count": EXPECTED_STANDARD_ETFS,
        "remediation_registrant_count": EXPECTED_REMEDIATION_GROUPS,
        "remediation_etf_count": EXPECTED_REMEDIATION_ETFS,
        "lane_group_counts": dict(sorted(lane_counts.items())),
        "lane_etf_counts": dict(sorted(etf_lane_counts.items())),
        "live_network_requested": live_network_requested,
        "live_capture_authorized": live_authorized,
        "network_requests_performed": 0,
        "sec_requests_performed": 0,
        "taxonomy_classification_performed": 0,
        "taxonomy_normalization_performed": 0,
        "execution_manifest_complete": True,
        "next_required_step": (
            "AUTHORIZE_AND_EXECUTE_LIVE_CAPTURE"
            if live_authorized
            else "LIVE_CAPTURE_AUTHORIZATION_REQUIRED"
        ),
    }

    return {
        "artifact_id": "ETF_1077_AUTHORITATIVE_CAPTURE_EXECUTION_MANIFEST",
        "summary": summary,
        "execution_groups": execution_groups,
    }
