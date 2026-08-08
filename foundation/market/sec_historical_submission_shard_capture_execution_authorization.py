from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class HistoricalShardAuthorizationError(ValueError):
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
        raise HistoricalShardAuthorizationError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def validate_manifest(
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    policy: dict[str, Any],
    governed_head: str,
) -> None:
    if governed_head != policy[
        "required_governed_head"
    ]:
        raise HistoricalShardAuthorizationError(
            "GOVERNED_HEAD_MISMATCH"
        )

    if (
        sha256_bytes(manifest_bytes)
        != policy[
            "required_manifest_sha256"
        ]
    ):
        raise HistoricalShardAuthorizationError(
            "MANIFEST_SHA256_MISMATCH"
        )

    if manifest.get("phase") != "3.6b.3r":
        raise HistoricalShardAuthorizationError(
            "MANIFEST_PHASE_MISMATCH"
        )

    if list(
        manifest.get(
            "target_symbols",
            [],
        )
    ) != list(
        policy[
            "required_target_symbols"
        ]
    ):
        raise HistoricalShardAuthorizationError(
            "TARGET_SCOPE_MISMATCH"
        )

    if int(
        manifest.get(
            "historical_shard_count",
            -1,
        )
    ) != int(
        policy[
            "required_shard_count"
        ]
    ):
        raise HistoricalShardAuthorizationError(
            "SHARD_COUNT_MISMATCH"
        )

    execution = manifest[
        "execution_contract"
    ]

    expected = policy[
        "execution_contract"
    ]

    for key in (
        "maximum_unique_sec_requests",
        "maximum_requests_per_second",
        "maximum_retry_attempts",
        "cache_identical_requests",
        "immutable_raw_storage",
    ):
        if execution[key] != expected[key]:
            raise HistoricalShardAuthorizationError(
                f"EXECUTION_CONTRACT_MISMATCH:{key}"
            )

    authority = manifest[
        "authority"
    ]

    for key in (
        "historical_shard_network_capture_authorized",
        "filing_header_capture_authorized",
        "filing_document_capture_authorized",
        "expanded_recent_filing_scan_authorized",
        "full_priority_population_execution_authorized",
        "taxonomy_evidence_normalization_authorized",
        "production_taxonomy_classification_authorized",
        "ranking_authorized",
        "recommendations_authorized",
        "portfolio_allocation_authorized",
        "automatic_execution_authorized",
        "uip_database_write_authorized",
    ):
        if authority.get(key) is not False:
            raise HistoricalShardAuthorizationError(
                f"MANIFEST_PROHIBITED_AUTHORITY_ENABLED:{key}"
            )

    shards = list(
        manifest.get(
            "historical_shards",
            [],
        )
    )

    if len(shards) != 12:
        raise HistoricalShardAuthorizationError(
            "EXACT_12_SHARDS_REQUIRED"
        )

    expected_names = [
        f"CIK0001100663-submissions-{index:03d}.json"
        for index in range(1, 13)
    ]

    actual_names = [
        str(item.get("filename"))
        for item in shards
    ]

    if actual_names != expected_names:
        raise HistoricalShardAuthorizationError(
            "SHARD_FILENAME_SCOPE_MISMATCH"
        )

    expected_urls = [
        "https://data.sec.gov/submissions/"
        + name
        for name in expected_names
    ]

    actual_urls = [
        str(item.get("url"))
        for item in shards
    ]

    if actual_urls != expected_urls:
        raise HistoricalShardAuthorizationError(
            "SHARD_URL_SCOPE_MISMATCH"
        )


def build_authorization(
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    policy: dict[str, Any],
    governed_head: str,
) -> dict[str, Any]:
    validate_manifest(
        manifest,
        manifest_bytes,
        policy,
        governed_head,
    )

    return {
        "artifact_id": (
            "SEC_HISTORICAL_SUBMISSION_SHARD_"
            "CAPTURE_EXECUTION_AUTHORIZATION"
        ),
        "phase": "3.6b.3r",
        "operating_date": policy[
            "operating_date"
        ],
        "operating_timezone": policy[
            "operating_timezone"
        ],
        "governed_head": governed_head,
        "manifest_sha256": sha256_bytes(
            manifest_bytes
        ),
        "authorized_symbols": deepcopy(
            policy[
                "required_target_symbols"
            ]
        ),
        "authorized_shard_count": int(
            policy[
                "required_shard_count"
            ]
        ),
        "execution_contract": deepcopy(
            policy[
                "execution_contract"
            ]
        ),
        "scope_controls": deepcopy(
            policy[
                "scope_controls"
            ]
        ),
        "authority": deepcopy(
            policy[
                "authority"
            ]
        ),
        "network_capture_authorized": True,
        "automatic_execution_authorized": False,
        "filing_header_capture_authorized": False,
        "filing_document_capture_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "authorization_complete": True,
        "critical_failures": [],
        "network_requests_performed": 0,
        "next_required_step": (
            "EXECUTE_EXACT_12_HISTORICAL_"
            "SUBMISSION_SHARD_CAPTURE"
        ),
    }


def write_outputs(
    authorization: dict[str, Any],
    output_path: str | Path,
    summary_path: str | Path,
) -> dict[str, Any]:
    output = Path(
        output_path
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
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
        output.read_bytes()
    )

    summary = {
        "artifact_id": (
            "SEC_HISTORICAL_SUBMISSION_SHARD_"
            "CAPTURE_EXECUTION_AUTHORIZATION_SUMMARY"
        ),
        "phase": authorization[
            "phase"
        ],
        "authorization_complete": True,
        "governed_head": authorization[
            "governed_head"
        ],
        "manifest_sha256": authorization[
            "manifest_sha256"
        ],
        "authorized_symbols": authorization[
            "authorized_symbols"
        ],
        "authorized_shard_count": authorization[
            "authorized_shard_count"
        ],
        "maximum_unique_sec_requests": (
            authorization[
                "execution_contract"
            ][
                "maximum_unique_sec_requests"
            ]
        ),
        "maximum_requests_per_second": (
            authorization[
                "execution_contract"
            ][
                "maximum_requests_per_second"
            ]
        ),
        "maximum_retry_attempts": (
            authorization[
                "execution_contract"
            ][
                "maximum_retry_attempts"
            ]
        ),
        "request_timeout_seconds": (
            authorization[
                "execution_contract"
            ][
                "request_timeout_seconds"
            ]
        ),
        "network_capture_authorized": True,
        "automatic_execution_authorized": False,
        "filing_header_capture_authorized": False,
        "filing_document_capture_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "network_requests_performed": 0,
        "authorization_sha256": (
            authorization_sha
        ),
        "next_required_step": authorization[
            "next_required_step"
        ],
    }

    target = Path(
        summary_path
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return summary
