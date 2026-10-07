from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class SeriesClassPilotAuthorizationError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(value, dict):
        raise SeriesClassPilotAuthorizationError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def validate_resolution_policy(
    resolution_policy: dict[str, Any],
    resolution_policy_bytes: bytes,
    authorization_policy: dict[str, Any],
    governed_head: str,
) -> None:
    if governed_head != authorization_policy["required_governed_head"]:
        raise SeriesClassPilotAuthorizationError(
            "GOVERNED_HEAD_MISMATCH"
        )

    if (
        sha256_bytes(resolution_policy_bytes)
        != authorization_policy["required_resolution_policy_sha256"]
    ):
        raise SeriesClassPilotAuthorizationError(
            "RESOLUTION_POLICY_SHA256_MISMATCH"
        )

    if (
        resolution_policy.get("required_remediation_ledger_sha256")
        != authorization_policy["required_remediation_ledger_sha256"]
    ):
        raise SeriesClassPilotAuthorizationError(
            "INPUT_LEDGER_SHA256_MISMATCH"
        )

    if (
        int(resolution_policy.get("required_pilot_record_count", -1))
        != int(authorization_policy["required_record_count"])
    ):
        raise SeriesClassPilotAuthorizationError(
            "RECORD_COUNT_MISMATCH"
        )

    if (
        list(resolution_policy.get("pilot_symbols", []))
        != list(authorization_policy["required_symbols"])
    ):
        raise SeriesClassPilotAuthorizationError(
            "SYMBOL_SCOPE_MISMATCH"
        )

    route = resolution_policy["route"]
    execution = resolution_policy["execution"]
    expected = authorization_policy["execution_contract"]

    checks = {
        "maximum_recent_filings_scanned": route["maximum_recent_filings_scanned"],
        "maximum_documents_per_filing": route["maximum_documents_per_filing"],
        "maximum_total_sec_requests": execution["maximum_total_sec_requests"],
        "maximum_requests_per_second": execution["maximum_requests_per_second"],
        "maximum_retry_attempts": execution["maximum_retry_attempts"],
        "request_timeout_seconds": execution["request_timeout_seconds"],
        "cache_identical_requests": execution["cache_identical_requests"],
        "immutable_raw_storage": execution["immutable_raw_storage"],
        "pilot_only": execution["pilot_only"],
    }

    for key, actual in checks.items():
        if actual != expected[key]:
            raise SeriesClassPilotAuthorizationError(
                f"EXECUTION_CONTRACT_MISMATCH:{key}"
            )

    if list(route["required_identity_markers"]) != [
        "sec_series_id",
        "sec_class_contract_id",
    ]:
        raise SeriesClassPilotAuthorizationError(
            "REQUIRED_IDENTITY_CONTRACT_MISMATCH"
        )

    if list(route["supporting_identity_markers"]) != [
        "symbol",
        "sec_cik",
    ]:
        raise SeriesClassPilotAuthorizationError(
            "SUPPORTING_IDENTITY_CONTRACT_MISMATCH"
        )

    authority = resolution_policy["authority"]

    prohibited = [
        "series_class_route_reliability_certification",
        "full_priority_batch_recapture",
        "capture_ledger_certification",
        "taxonomy_evidence_normalization",
        "production_taxonomy_classification",
        "relative_return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    ]

    for key in prohibited:
        if authority.get(key) is not False:
            raise SeriesClassPilotAuthorizationError(
                f"PROHIBITED_AUTHORITY_ENABLED:{key}"
            )


def build_authorization(
    resolution_policy: dict[str, Any],
    resolution_policy_bytes: bytes,
    authorization_policy: dict[str, Any],
    governed_head: str,
) -> dict[str, Any]:
    validate_resolution_policy(
        resolution_policy,
        resolution_policy_bytes,
        authorization_policy,
        governed_head,
    )

    return {
        "artifact_id": (
            "SEC_SERIES_CLASS_RESOLUTION_"
            "PILOT_EXECUTION_AUTHORIZATION"
        ),
        "phase": "3.6b.3p",
        "operating_date": authorization_policy["operating_date"],
        "operating_timezone": authorization_policy["operating_timezone"],
        "governed_head": governed_head,
        "resolution_policy_sha256": sha256_bytes(
            resolution_policy_bytes
        ),
        "remediation_ledger_sha256": (
            authorization_policy["required_remediation_ledger_sha256"]
        ),
        "authorized_record_count": (
            authorization_policy["required_record_count"]
        ),
        "authorized_symbols": deepcopy(
            authorization_policy["required_symbols"]
        ),
        "execution_contract": deepcopy(
            authorization_policy["execution_contract"]
        ),
        "identity_contract": deepcopy(
            authorization_policy["identity_contract"]
        ),
        "scope_controls": deepcopy(
            authorization_policy["scope_controls"]
        ),
        "authority": deepcopy(
            authorization_policy["authority"]
        ),
        "network_capture_authorized": True,
        "automatic_execution_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "authorization_complete": True,
        "critical_failures": [],
        "next_required_step": (
            "EXECUTE_FIVE_SECURITY_"
            "SERIES_CLASS_RESOLUTION_PILOT"
        ),
    }


def write_outputs(
    authorization: dict[str, Any],
    output_path: Path,
    summary_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            authorization,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    authorization_sha = sha256_bytes(
        output_path.read_bytes()
    )

    summary = {
        "artifact_id": (
            "SEC_SERIES_CLASS_RESOLUTION_"
            "PILOT_EXECUTION_AUTHORIZATION_SUMMARY"
        ),
        "authorization_complete": True,
        "authorized_record_count": authorization["authorized_record_count"],
        "authorized_symbols": authorization["authorized_symbols"],
        "governed_head": authorization["governed_head"],
        "resolution_policy_sha256": authorization["resolution_policy_sha256"],
        "remediation_ledger_sha256": authorization["remediation_ledger_sha256"],
        "maximum_recent_filings_scanned": (
            authorization["execution_contract"]["maximum_recent_filings_scanned"]
        ),
        "maximum_documents_per_filing": (
            authorization["execution_contract"]["maximum_documents_per_filing"]
        ),
        "maximum_total_sec_requests": (
            authorization["execution_contract"]["maximum_total_sec_requests"]
        ),
        "maximum_requests_per_second": (
            authorization["execution_contract"]["maximum_requests_per_second"]
        ),
        "maximum_retry_attempts": (
            authorization["execution_contract"]["maximum_retry_attempts"]
        ),
        "network_capture_authorized": True,
        "automatic_execution_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "authorization_sha256": authorization_sha,
        "next_required_step": authorization["next_required_step"],
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
