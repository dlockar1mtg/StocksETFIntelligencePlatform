from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from foundation.market.sec_historical_series_class_header_capture import (
    fetch_once,
)


EXPECTED_PLAN_ARTIFACT = (
    "ETF_849_UNRESOLVED_STANDARD_HISTORICAL_METADATA_PLAN"
)

EXPECTED_AUTHORIZATION_ID = (
    "ETF_849_HISTORICAL_METADATA_CAPTURE_AUTHORIZATION_V1"
)

EXPECTED_TARGET_ETFS = 849
EXPECTED_TARGET_REGISTRANTS = 92
EXPECTED_REGISTRANTS_WITH_SHARDS = 69
EXPECTED_SHARDS = 102
EXPECTED_REPORTED_FILINGS = 126873

ALLOWED_FORMS = {
    "N-1A",
    "N-1A/A",
    "497",
    "497K",
    "485APOS",
    "485BPOS",
}


class HistoricalMetadataCaptureError(
    RuntimeError
):
    pass


FetchFunction = Callable[
    [str, str, int],
    tuple[int, str, bytes],
]


def sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def sha256_path(
    path: str | Path,
) -> str:
    return sha256_bytes(
        Path(path).read_bytes()
    )


def load_json(
    path: str | Path,
) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise HistoricalMetadataCaptureError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def _atomic_write_json(
    path: str | Path,
    value: dict[str, Any],
) -> None:
    target = Path(
        path
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = target.with_suffix(
        target.suffix + ".tmp"
    )

    payload = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode(
        "utf-8"
    )

    temporary.write_bytes(
        payload
    )

    os.replace(
        temporary,
        target,
    )


def validate_plan(
    plan: dict[str, Any],
    *,
    plan_sha256: str,
    expected_plan_sha256: str,
) -> list[dict[str, Any]]:

    if (
        plan_sha256
        != expected_plan_sha256
    ):
        raise HistoricalMetadataCaptureError(
            "PLAN_SHA256_MISMATCH"
        )

    if (
        plan.get(
            "artifact_id"
        )
        != EXPECTED_PLAN_ARTIFACT
    ):
        raise HistoricalMetadataCaptureError(
            "PLAN_ARTIFACT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "historical_remediation_target_count",
                -1,
            )
        )
        != EXPECTED_TARGET_ETFS
    ):
        raise HistoricalMetadataCaptureError(
            "HISTORICAL_TARGET_COUNT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "historical_target_registrant_count",
                -1,
            )
        )
        != EXPECTED_TARGET_REGISTRANTS
    ):
        raise HistoricalMetadataCaptureError(
            "HISTORICAL_REGISTRANT_COUNT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "historical_submission_shard_count",
                -1,
            )
        )
        != EXPECTED_SHARDS
    ):
        raise HistoricalMetadataCaptureError(
            "HISTORICAL_SHARD_COUNT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "reported_historical_filing_count",
                -1,
            )
        )
        != EXPECTED_REPORTED_FILINGS
    ):
        raise HistoricalMetadataCaptureError(
            "REPORTED_HISTORICAL_FILING_COUNT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "preserved_resolved_standard_count",
                -1,
            )
        )
        != 9
    ):
        raise HistoricalMetadataCaptureError(
            "PRESERVED_RESOLVED_COUNT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "preserved_conflicted_standard_count",
                -1,
            )
        )
        != 4
    ):
        raise HistoricalMetadataCaptureError(
            "PRESERVED_CONFLICTED_COUNT_MISMATCH"
        )

    if (
        int(
            plan.get(
                "delegated_priority_remediation_count",
                -1,
            )
        )
        != 215
    ):
        raise HistoricalMetadataCaptureError(
            "DELEGATED_REMEDIATION_COUNT_MISMATCH"
        )

    if (
        plan.get(
            "historical_shard_capture_authorized"
        )
        is not False
    ):
        raise HistoricalMetadataCaptureError(
            "PLAN_MAY_NOT_SELF_AUTHORIZE_CAPTURE"
        )

    if (
        plan.get(
            "historical_filing_document_capture_authorized"
        )
        is not False
    ):
        raise HistoricalMetadataCaptureError(
            "PLAN_MAY_NOT_AUTHORIZE_DOCUMENT_CAPTURE"
        )

    if (
        plan.get(
            "production_taxonomy_classification_authorized"
        )
        is not False
    ):
        raise HistoricalMetadataCaptureError(
            "PLAN_MAY_NOT_AUTHORIZE_CLASSIFICATION"
        )

    if (
        plan.get(
            "taxonomy_normalization_authorized"
        )
        is not False
    ):
        raise HistoricalMetadataCaptureError(
            "PLAN_MAY_NOT_AUTHORIZE_NORMALIZATION"
        )

    sources = plan.get(
        "registrant_sources"
    )

    if not isinstance(
        sources,
        list,
    ):
        raise HistoricalMetadataCaptureError(
            "REGISTRANT_SOURCES_REQUIRED"
        )

    shards: list[
        dict[str, Any]
    ] = []

    registrants_with_shards = set()

    for source in sources:
        cik = str(
            source.get(
                "sec_cik"
            )
            or ""
        )

        historical_shards = (
            source.get(
                "historical_shards"
            )
        )

        if not isinstance(
            historical_shards,
            list,
        ):
            raise HistoricalMetadataCaptureError(
                "HISTORICAL_SHARDS_MUST_BE_LIST"
            )

        if historical_shards:
            registrants_with_shards.add(
                cik
            )

        for shard in historical_shards:
            if not isinstance(
                shard,
                dict,
            ):
                raise HistoricalMetadataCaptureError(
                    "HISTORICAL_SHARD_OBJECT_REQUIRED"
                )

            if (
                str(
                    shard.get(
                        "sec_cik"
                    )
                    or ""
                )
                != cik
            ):
                raise HistoricalMetadataCaptureError(
                    "HISTORICAL_SHARD_CIK_MISMATCH"
                )

            filename = str(
                shard.get(
                    "historical_submissions_file"
                )
                or ""
            )

            url = str(
                shard.get(
                    "historical_submissions_url"
                )
                or ""
            )

            if (
                not filename
                or not filename.endswith(
                    ".json"
                )
            ):
                raise HistoricalMetadataCaptureError(
                    "INVALID_HISTORICAL_SHARD_FILENAME"
                )

            expected_url = (
                "https://data.sec.gov/submissions/"
                + filename
            )

            if url != expected_url:
                raise HistoricalMetadataCaptureError(
                    "HISTORICAL_SHARD_URL_MISMATCH"
                )

            shards.append(
                {
                    "sec_cik":
                        cik,

                    "historical_submissions_file":
                        filename,

                    "historical_submissions_url":
                        url,

                    "reported_filing_count":
                        int(
                            shard.get(
                                "reported_filing_count"
                            )
                            or 0
                        ),

                    "filing_from":
                        shard.get(
                            "filing_from"
                        ),

                    "filing_to":
                        shard.get(
                            "filing_to"
                        ),
                }
            )

    if (
        len(
            registrants_with_shards
        )
        != EXPECTED_REGISTRANTS_WITH_SHARDS
    ):
        raise HistoricalMetadataCaptureError(
            "REGISTRANTS_WITH_SHARDS_COUNT_MISMATCH"
        )

    if len(
        shards
    ) != EXPECTED_SHARDS:
        raise HistoricalMetadataCaptureError(
            "EXACT_102_SHARDS_REQUIRED"
        )

    keys = [
        (
            shard[
                "sec_cik"
            ],
            shard[
                "historical_submissions_file"
            ],
        )
        for shard
        in shards
    ]

    if len(
        keys
    ) != len(
        set(
            keys
        )
    ):
        raise HistoricalMetadataCaptureError(
            "DUPLICATE_HISTORICAL_SHARD"
        )

    urls = [
        shard[
            "historical_submissions_url"
        ]
        for shard
        in shards
    ]

    if len(
        urls
    ) != len(
        set(
            urls
        )
    ):
        raise HistoricalMetadataCaptureError(
            "DUPLICATE_HISTORICAL_SHARD_URL"
        )

    return sorted(
        shards,
        key=lambda value: (
            value[
                "sec_cik"
            ],
            value[
                "historical_submissions_file"
            ],
        ),
    )


def validate_authorization(
    authorization: dict[str, Any],
    *,
    plan_sha256: str,
) -> None:

    if (
        authorization.get(
            "authorization_id"
        )
        != EXPECTED_AUTHORIZATION_ID
    ):
        raise HistoricalMetadataCaptureError(
            "AUTHORIZATION_ID_MISMATCH"
        )

    if (
        authorization.get(
            "authorization_version"
        )
        != "1.0.0"
    ):
        raise HistoricalMetadataCaptureError(
            "AUTHORIZATION_VERSION_MISMATCH"
        )

    if (
        authorization.get(
            "execution_state"
        )
        != "AUTHORIZED_FOR_HISTORICAL_METADATA_CAPTURE"
    ):
        raise HistoricalMetadataCaptureError(
            "AUTHORIZATION_STATE_MISMATCH"
        )

    if (
        authorization.get(
            "historical_plan_sha256"
        )
        != plan_sha256
    ):
        raise HistoricalMetadataCaptureError(
            "AUTHORIZATION_PLAN_SHA_MISMATCH"
        )

    exact_counts = {
        "historical_target_etf_count":
            EXPECTED_TARGET_ETFS,

        "historical_target_registrant_count":
            EXPECTED_TARGET_REGISTRANTS,

        "registrants_with_historical_shards":
            EXPECTED_REGISTRANTS_WITH_SHARDS,

        "historical_submission_shard_count":
            EXPECTED_SHARDS,

        "reported_historical_filing_count":
            EXPECTED_REPORTED_FILINGS,

        "maximum_unique_sec_requests":
            EXPECTED_SHARDS,

        "maximum_retry_attempts":
            0,
    }

    for field, expected in (
        exact_counts.items()
    ):
        if int(
            authorization.get(
                field,
                -1,
            )
        ) != expected:
            raise HistoricalMetadataCaptureError(
                "AUTHORIZATION_COUNT_MISMATCH:"
                + field
            )

    for field in (
        "network_capture_authorized",
        "historical_submission_metadata_capture_authorized",
        "cache_identical_requests",
        "resume_safe_checkpoint_required",
        "immutable_raw_storage",
        "content_addressed_raw_storage",
    ):
        if (
            authorization.get(
                field
            )
            is not True
        ):
            raise HistoricalMetadataCaptureError(
                "REQUIRED_AUTHORIZATION_CONTROL_DISABLED:"
                + field
            )

    for field in (
        "historical_filing_document_capture_authorized",
        "production_taxonomy_classification_authorized",
        "taxonomy_normalization_authorized",
        "ranking_authorized",
        "recommendations_authorized",
        "portfolio_allocation_authorized",
        "automatic_execution_authorized",
    ):
        if (
            authorization.get(
                field
            )
            is not False
        ):
            raise HistoricalMetadataCaptureError(
                "PROHIBITED_AUTHORITY_OPEN:"
                + field
            )

    rate = float(
        authorization.get(
            "maximum_requests_per_second",
            0,
        )
    )

    if (
        rate <= 0
        or rate > 10
    ):
        raise HistoricalMetadataCaptureError(
            "INVALID_REQUEST_RATE"
        )

    if (
        int(
            authorization.get(
                "request_timeout_seconds",
                0,
            )
        )
        < 1
    ):
        raise HistoricalMetadataCaptureError(
            "INVALID_REQUEST_TIMEOUT"
        )


def parse_historical_shard(
    payload: bytes,
) -> dict[str, Any]:

    try:
        value = json.loads(
            payload.decode(
                "utf-8-sig"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise HistoricalMetadataCaptureError(
            "INVALID_HISTORICAL_SHARD_JSON"
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise HistoricalMetadataCaptureError(
            "HISTORICAL_SHARD_OBJECT_REQUIRED"
        )

    fields = {
        "accessionNumber":
            value.get(
                "accessionNumber",
                []
            ),

        "filingDate":
            value.get(
                "filingDate",
                []
            ),

        "form":
            value.get(
                "form",
                []
            ),

        "primaryDocument":
            value.get(
                "primaryDocument",
                []
            ),
    }

    for name, items in (
        fields.items()
    ):
        if not isinstance(
            items,
            list,
        ):
            raise HistoricalMetadataCaptureError(
                "HISTORICAL_FIELD_NOT_LIST:"
                + name
            )

    lengths = {
        len(
            items
        )
        for items
        in fields.values()
    }

    if len(
        lengths
    ) > 1:
        raise HistoricalMetadataCaptureError(
            "HISTORICAL_FIELD_LENGTH_MISMATCH"
        )

    allowed_count = sum(
        1
        for form
        in fields[
            "form"
        ]
        if form
        in ALLOWED_FORMS
    )

    return {
        "filing_count":
            len(
                fields[
                    "form"
                ]
            ),

        "allowed_form_filing_count":
            allowed_count,
    }


def build_offline_plan(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    *,
    plan_sha256: str,
) -> dict[str, Any]:

    shards = validate_plan(
        plan,
        plan_sha256=
            plan_sha256,
        expected_plan_sha256=
            authorization.get(
                "historical_plan_sha256",
                "",
            ),
    )

    validate_authorization(
        authorization,
        plan_sha256=
            plan_sha256,
    )

    return {
        "artifact_id":
            "ETF_849_HISTORICAL_METADATA_CAPTURE_EXECUTION_PLAN",

        "historical_target_etf_count":
            EXPECTED_TARGET_ETFS,

        "historical_target_registrant_count":
            EXPECTED_TARGET_REGISTRANTS,

        "registrants_with_historical_shards":
            EXPECTED_REGISTRANTS_WITH_SHARDS,

        "historical_submission_shard_count":
            len(
                shards
            ),

        "maximum_unique_sec_requests":
            int(
                authorization[
                    "maximum_unique_sec_requests"
                ]
            ),

        "maximum_requests_per_second":
            float(
                authorization[
                    "maximum_requests_per_second"
                ]
            ),

        "filing_document_requests_authorized":
            False,

        "taxonomy_classification_authorized":
            False,

        "taxonomy_normalization_authorized":
            False,

        "network_requests_performed":
            0,
    }


def _load_checkpoint(
    checkpoint_path: Path,
    *,
    plan_sha256: str,
    authorization_version: str,
) -> dict[str, Any]:

    if not checkpoint_path.exists():
        return {
            "artifact_id":
                "ETF_849_HISTORICAL_METADATA_CAPTURE_CHECKPOINT",

            "plan_sha256":
                plan_sha256,

            "authorization_version":
                authorization_version,

            "completed":
                {},
        }

    checkpoint = load_json(
        checkpoint_path
    )

    if (
        checkpoint.get(
            "artifact_id"
        )
        != "ETF_849_HISTORICAL_METADATA_CAPTURE_CHECKPOINT"
    ):
        raise HistoricalMetadataCaptureError(
            "CHECKPOINT_ARTIFACT_MISMATCH"
        )

    if (
        checkpoint.get(
            "plan_sha256"
        )
        != plan_sha256
    ):
        raise HistoricalMetadataCaptureError(
            "CHECKPOINT_PLAN_SHA_MISMATCH"
        )

    if (
        checkpoint.get(
            "authorization_version"
        )
        != authorization_version
    ):
        raise HistoricalMetadataCaptureError(
            "CHECKPOINT_AUTHORIZATION_VERSION_MISMATCH"
        )

    completed = checkpoint.get(
        "completed"
    )

    if not isinstance(
        completed,
        dict,
    ):
        raise HistoricalMetadataCaptureError(
            "CHECKPOINT_COMPLETED_OBJECT_REQUIRED"
        )

    return checkpoint


def capture_historical_metadata(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    *,
    plan_sha256: str,
    raw_root: str | Path,
    checkpoint_path: str | Path,
    user_agent: str,
    fetcher: FetchFunction = fetch_once,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:

    shards = validate_plan(
        plan,
        plan_sha256=
            plan_sha256,
        expected_plan_sha256=
            authorization.get(
                "historical_plan_sha256",
                "",
            ),
    )

    validate_authorization(
        authorization,
        plan_sha256=
            plan_sha256,
    )

    if (
        not user_agent
        or "@"
        not in user_agent
        or len(
            user_agent.strip()
        )
        < 12
    ):
        raise HistoricalMetadataCaptureError(
            "IDENTIFYING_SEC_USER_AGENT_REQUIRED"
        )

    root = Path(
        raw_root
    )

    checkpoint_target = Path(
        checkpoint_path
    )

    checkpoint = _load_checkpoint(
        checkpoint_target,
        plan_sha256=
            plan_sha256,
        authorization_version=
            authorization[
                "authorization_version"
            ],
    )

    completed = checkpoint[
        "completed"
    ]

    maximum_requests = int(
        authorization[
            "maximum_unique_sec_requests"
        ]
    )

    rate = float(
        authorization[
            "maximum_requests_per_second"
        ]
    )

    timeout = int(
        authorization[
            "request_timeout_seconds"
        ]
    )

    current_run_requests = 0

    output_records = []

    for shard in shards:
        url = shard[
            "historical_submissions_url"
        ]

        existing = completed.get(
            url
        )

        if existing is not None:
            raw_path = Path(
                existing[
                    "raw_path"
                ]
            )

            if not raw_path.is_file():
                raise HistoricalMetadataCaptureError(
                    "CHECKPOINT_RAW_FILE_MISSING:"
                    + str(
                        raw_path
                    )
                )

            payload = raw_path.read_bytes()

            if (
                sha256_bytes(
                    payload
                )
                != existing[
                    "content_sha256"
                ]
            ):
                raise HistoricalMetadataCaptureError(
                    "CHECKPOINT_RAW_HASH_MISMATCH:"
                    + url
                )

            parsed = parse_historical_shard(
                payload
            )

            output_records.append(
                {
                    **shard,
                    **existing,
                    **parsed,
                    "resume_reused":
                        True,
                }
            )

            continue

        if (
            current_run_requests
            >= maximum_requests
        ):
            raise HistoricalMetadataCaptureError(
                "ABSOLUTE_102_REQUEST_CEILING_EXHAUSTED"
            )

        if current_run_requests > 0:
            sleeper(
                1.0
                / rate
            )

        (
            status,
            final_url,
            payload,
        ) = fetcher(
            url,
            user_agent.strip(),
            timeout,
        )

        current_run_requests += 1

        if int(
            status
        ) != 200:
            raise HistoricalMetadataCaptureError(
                "SEC_HTTP_FAILURE:"
                + str(
                    status
                )
                + ":"
                + url
            )

        if not payload:
            raise HistoricalMetadataCaptureError(
                "SEC_EMPTY_PAYLOAD:"
                + url
            )

        parsed = parse_historical_shard(
            payload
        )

        content_sha = sha256_bytes(
            payload
        )

        raw_path = (
            root
            / "sec_taxonomy"
            / "historical_submissions"
            / (
                "CIK"
                + shard[
                    "sec_cik"
                ]
            )
            / (
                Path(
                    shard[
                        "historical_submissions_file"
                    ]
                ).stem
            )
            / (
                content_sha
                + ".json"
            )
        )

        raw_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if raw_path.exists():
            existing_payload = (
                raw_path.read_bytes()
            )

            if (
                existing_payload
                != payload
            ):
                raise HistoricalMetadataCaptureError(
                    "IMMUTABLE_RAW_COLLISION:"
                    + str(
                        raw_path
                    )
                )

        else:
            raw_path.write_bytes(
                payload
            )

        completed_record = {
            "http_status":
                int(
                    status
                ),

            "final_url":
                str(
                    final_url
                ),

            "content_sha256":
                content_sha,

            "raw_path":
                str(
                    raw_path
                ),

            "byte_count":
                len(
                    payload
                ),
        }

        completed[
            url
        ] = completed_record

        _atomic_write_json(
            checkpoint_target,
            checkpoint,
        )

        output_records.append(
            {
                **shard,
                **completed_record,
                **parsed,
                "resume_reused":
                    False,
            }
        )

    if len(
        output_records
    ) != EXPECTED_SHARDS:
        raise HistoricalMetadataCaptureError(
            "FINAL_102_SHARD_ACCOUNTING_MISMATCH"
        )

    total_filing_count = sum(
        int(
            record[
                "filing_count"
            ]
        )
        for record
        in output_records
    )

    total_allowed_form_count = sum(
        int(
            record[
                "allowed_form_filing_count"
            ]
        )
        for record
        in output_records
    )

    return {
        "artifact_id":
            "ETF_849_HISTORICAL_METADATA_CAPTURE_LEDGER",

        "plan_sha256":
            plan_sha256,

        "historical_target_etf_count":
            EXPECTED_TARGET_ETFS,

        "historical_target_registrant_count":
            EXPECTED_TARGET_REGISTRANTS,

        "registrants_with_historical_shards":
            EXPECTED_REGISTRANTS_WITH_SHARDS,

        "historical_submission_shard_count":
            EXPECTED_SHARDS,

        "captured_shard_count":
            len(
                output_records
            ),

        "current_run_sec_requests_performed":
            current_run_requests,

        "total_completed_shards":
            len(
                completed
            ),

        "historical_filing_metadata_count":
            total_filing_count,

        "allowed_form_filing_metadata_count":
            total_allowed_form_count,

        "filing_document_requests_performed":
            0,

        "taxonomy_classification_performed":
            0,

        "taxonomy_normalization_performed":
            0,

        "records":
            output_records,
    }
