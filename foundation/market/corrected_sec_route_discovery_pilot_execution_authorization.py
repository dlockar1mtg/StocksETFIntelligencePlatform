from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class CorrectedPilotAuthorizationError(ValueError):
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
        raise CorrectedPilotAuthorizationError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def validate_manifest(
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    policy: dict[str, Any],
    governed_head: str,
) -> list[dict[str, Any]]:
    if governed_head != policy["required_governed_head"]:
        raise CorrectedPilotAuthorizationError(
            "GOVERNED_HEAD_MISMATCH"
        )

    if (
        sha256_bytes(manifest_bytes)
        != policy["required_manifest_sha256"]
    ):
        raise CorrectedPilotAuthorizationError(
            "MANIFEST_SHA256_MISMATCH"
        )

    if (
        manifest.get("artifact_id")
        != policy["required_manifest_artifact_id"]
    ):
        raise CorrectedPilotAuthorizationError(
            "MANIFEST_ARTIFACT_ID_MISMATCH"
        )

    if (
        manifest.get("network_execution_authorized")
        is not False
    ):
        raise CorrectedPilotAuthorizationError(
            "MANIFEST_PREMATURE_NETWORK_AUTHORITY"
        )

    records = list(
        manifest.get("records", [])
    )

    required_count = int(
        policy["required_record_count"]
    )

    if (
        int(
            manifest.get(
                "pilot_record_count",
                -1,
            )
        )
        != required_count
        or len(records) != required_count
    ):
        raise CorrectedPilotAuthorizationError(
            "PILOT_RECORD_COUNT_MISMATCH"
        )

    required_symbols = list(
        policy["required_symbols"]
    )

    symbols = [
        str(record.get("symbol") or "")
        for record in records
    ]

    if symbols != required_symbols:
        raise CorrectedPilotAuthorizationError(
            "PILOT_SYMBOL_SET_OR_ORDER_MISMATCH"
        )

    execution = policy["execution_contract"]

    manifest_contract = {
        "maximum_candidate_documents_per_security": (
            manifest.get(
                "maximum_candidate_documents_per_security"
            )
        ),
        "maximum_submissions_requests": (
            manifest.get(
                "maximum_submissions_requests"
            )
        ),
        "maximum_candidate_document_requests": (
            manifest.get(
                "maximum_candidate_document_requests"
            )
        ),
        "maximum_total_sec_requests": (
            manifest.get(
                "maximum_total_sec_requests"
            )
        ),
        "maximum_requests_per_second": (
            manifest.get(
                "maximum_requests_per_second"
            )
        ),
    }

    for key, value in manifest_contract.items():
        if value != execution[key]:
            raise CorrectedPilotAuthorizationError(
                f"EXECUTION_CONTRACT_MISMATCH:{key}"
            )

    security_ids: list[str] = []
    series_ids: list[str] = []
    class_ids: list[str] = []

    for record in records:
        for field in (
            "security_id",
            "symbol",
            "sec_cik",
            "sec_series_id",
            "sec_class_contract_id",
        ):
            if not record.get(field):
                raise CorrectedPilotAuthorizationError(
                    f"MISSING_IDENTITY:{field}"
                )

        if (
            record.get("remediation_queue")
            != "FILING_ROUTE_DISCOVERY_REQUIRED"
        ):
            raise CorrectedPilotAuthorizationError(
                "RECORD_OUTSIDE_DISCOVERY_QUEUE"
            )

        if (
            int(
                record.get(
                    "maximum_candidate_documents",
                    -1,
                )
            )
            != execution[
                "maximum_candidate_documents_per_security"
            ]
        ):
            raise CorrectedPilotAuthorizationError(
                "RECORD_CANDIDATE_LIMIT_MISMATCH"
            )

        if (
            record.get(
                "prior_candidate_route_reuse_authorized"
            )
            is not False
        ):
            raise CorrectedPilotAuthorizationError(
                "PRIOR_ROUTE_REUSE_AUTHORIZED"
            )

        if (
            record.get(
                "network_execution_authorized"
            )
            is not False
        ):
            raise CorrectedPilotAuthorizationError(
                "RECORD_PREMATURE_NETWORK_AUTHORITY"
            )

        security_ids.append(
            str(record["security_id"])
        )
        series_ids.append(
            str(record["sec_series_id"])
        )
        class_ids.append(
            str(
                record[
                    "sec_class_contract_id"
                ]
            )
        )

    if len(set(security_ids)) != required_count:
        raise CorrectedPilotAuthorizationError(
            "DUPLICATE_SECURITY_ID"
        )

    if len(set(series_ids)) != required_count:
        raise CorrectedPilotAuthorizationError(
            "DUPLICATE_SERIES_ID"
        )

    if len(set(class_ids)) != required_count:
        raise CorrectedPilotAuthorizationError(
            "DUPLICATE_CLASS_ID"
        )

    return records


def build_authorization(
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    policy: dict[str, Any],
    governed_head: str,
) -> dict[str, Any]:
    records = validate_manifest(
        manifest,
        manifest_bytes,
        policy,
        governed_head,
    )

    return {
        "artifact_id": (
            "CORRECTED_SEC_ROUTE_DISCOVERY_"
            "PILOT_EXECUTION_AUTHORIZATION"
        ),
        "operating_date": (
            policy["operating_date"]
        ),
        "operating_timezone": (
            policy["operating_timezone"]
        ),
        "governed_head": governed_head,
        "pilot_manifest_sha256": (
            sha256_bytes(
                manifest_bytes
            )
        ),
        "authorized_record_count": (
            len(records)
        ),
        "authorized_symbols": [
            record["symbol"]
            for record in records
        ],
        "authorized_security_ids": [
            record["security_id"]
            for record in records
        ],
        "execution_contract": deepcopy(
            policy["execution_contract"]
        ),
        "identity_contract": deepcopy(
            policy["identity_contract"]
        ),
        "scope_controls": deepcopy(
            policy["scope_controls"]
        ),
        "authority": deepcopy(
            policy["authority"]
        ),
        "network_capture_authorized": True,
        "automatic_execution_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "authorization_complete": True,
        "critical_failures": [],
        "next_required_step": (
            "EXECUTE_CORRECTED_FIVE_SECURITY_"
            "SEC_ROUTE_DISCOVERY_PILOT"
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

    summary = {
        "artifact_id": (
            "CORRECTED_SEC_ROUTE_DISCOVERY_"
            "PILOT_EXECUTION_AUTHORIZATION_SUMMARY"
        ),
        "authorization_complete": (
            authorization[
                "authorization_complete"
            ]
        ),
        "authorized_record_count": (
            authorization[
                "authorized_record_count"
            ]
        ),
        "authorized_symbols": (
            authorization[
                "authorized_symbols"
            ]
        ),
        "pilot_manifest_sha256": (
            authorization[
                "pilot_manifest_sha256"
            ]
        ),
        "network_capture_authorized": True,
        "automatic_execution_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "maximum_candidate_documents_per_security": (
            authorization[
                "execution_contract"
            ][
                "maximum_candidate_documents_per_security"
            ]
        ),
        "maximum_total_sec_requests": (
            authorization[
                "execution_contract"
            ][
                "maximum_total_sec_requests"
            ]
        ),
        "maximum_requests_per_second": (
            authorization[
                "execution_contract"
            ][
                "maximum_requests_per_second"
            ]
        ),
        "authorization_sha256": (
            sha256_bytes(
                output_path.read_bytes()
            )
        ),
        "next_required_step": (
            authorization[
                "next_required_step"
            ]
        ),
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
