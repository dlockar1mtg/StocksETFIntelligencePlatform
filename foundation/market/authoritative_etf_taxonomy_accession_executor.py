from __future__ import annotations

import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from foundation.market.authoritative_etf_taxonomy_sec_executor import (
    filing_document_url,
)
from foundation.market.sec_series_class_specific_filing_resolution import (
    choose_resolution,
    evaluate_candidate,
)


EXPECTED_GOVERNED_POPULATION = 1077
EXPECTED_UNRESOLVED_STANDARD = 849
EXPECTED_RESOLVED_STANDARD = 9
EXPECTED_CONFLICTED_STANDARD = 4
EXPECTED_REMEDIATION = 215

CHECKPOINT_ARTIFACT_ID = (
    "ETF_849_ACCESSION_CENTRIC_DOCUMENT_EXECUTION_CHECKPOINT"
)

EXECUTION_MODEL = (
    "FETCH_ACCESSION_ONCE_AND_EVALUATE_"
    "ALL_UNRESOLVED_IDENTITIES_FOR_CIK"
)


class AccessionCentricExecutorError(RuntimeError):
    pass


FetchFunction = Callable[
    [str, str, int],
    tuple[int, str, bytes],
]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_cik(value: Any) -> str:
    raw = str(value or "").strip()

    if raw.lower().startswith("sec-cik-"):
        raw = raw[8:]

    if not raw.isdigit():
        raise AccessionCentricExecutorError(
            f"INVALID_SEC_CIK:{value}"
        )

    return raw.zfill(10)


def _atomic_write_json(
    path: str | Path,
    value: dict[str, Any],
) -> None:
    target = Path(path)

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
    ).encode("utf-8")

    temporary.write_bytes(payload)

    maximum_replace_attempts = 8

    for attempt in range(
        maximum_replace_attempts
    ):
        try:
            os.replace(
                temporary,
                target,
            )
            break

        except PermissionError:
            if (
                attempt + 1
                >= maximum_replace_attempts
            ):
                raise

            time.sleep(
                0.05
                * (attempt + 1)
            )


def load_json(
    path: str | Path,
) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(value, dict):
        raise AccessionCentricExecutorError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def _identity_security_id(
    identity: dict[str, Any],
) -> str:
    value = str(
        identity.get("security_id")
        or ""
    ).strip()

    if not value:
        raise AccessionCentricExecutorError(
            "SECURITY_ID_REQUIRED"
        )

    return value


def validate_identity(
    identity: dict[str, Any],
) -> dict[str, Any]:
    required = (
        "security_id",
        "symbol",
        "sec_cik",
        "sec_series_id",
        "sec_class_contract_id",
    )

    for field in required:
        if not str(
            identity.get(field)
            or ""
        ).strip():
            raise AccessionCentricExecutorError(
                "INCOMPLETE_IDENTITY:"
                + field
            )

    normalized = dict(identity)

    normalized["sec_cik"] = (
        _normalize_cik(
            identity["sec_cik"]
        )
    )

    return normalized


def validate_population_partition(
    *,
    all_identities: Iterable[dict[str, Any]],
    unresolved_security_ids: Iterable[str],
    resolved_security_ids: Iterable[str],
    conflicted_security_ids: Iterable[str],
    remediation_security_ids: Iterable[str],
    enforce_production_counts: bool = True,
) -> dict[str, dict[str, Any]]:
    identities: dict[
        str,
        dict[str, Any],
    ] = {}

    for raw in all_identities:
        identity = validate_identity(
            raw
        )

        security_id = (
            _identity_security_id(
                identity
            )
        )

        if security_id in identities:
            raise AccessionCentricExecutorError(
                "DUPLICATE_SECURITY_ID:"
                + security_id
            )

        identities[
            security_id
        ] = identity

    partitions = {
        "unresolved": set(
            str(value)
            for value
            in unresolved_security_ids
        ),
        "resolved": set(
            str(value)
            for value
            in resolved_security_ids
        ),
        "conflicted": set(
            str(value)
            for value
            in conflicted_security_ids
        ),
        "remediation": set(
            str(value)
            for value
            in remediation_security_ids
        ),
    }

    names = list(
        partitions
    )

    for index, left_name in enumerate(
        names
    ):
        for right_name in names[
            index + 1:
        ]:
            overlap = (
                partitions[left_name]
                & partitions[right_name]
            )

            if overlap:
                raise AccessionCentricExecutorError(
                    "POPULATION_PARTITION_OVERLAP:"
                    + left_name
                    + ":"
                    + right_name
                )

    partition_union = set().union(
        *partitions.values()
    )

    identity_ids = set(
        identities
    )

    if partition_union != identity_ids:
        missing = sorted(
            identity_ids
            - partition_union
        )

        extra = sorted(
            partition_union
            - identity_ids
        )

        raise AccessionCentricExecutorError(
            "POPULATION_PARTITION_NOT_EXHAUSTIVE:"
            + f"MISSING={len(missing)}:"
            + f"EXTRA={len(extra)}"
        )

    if enforce_production_counts:
        expected = {
            "unresolved":
                EXPECTED_UNRESOLVED_STANDARD,
            "resolved":
                EXPECTED_RESOLVED_STANDARD,
            "conflicted":
                EXPECTED_CONFLICTED_STANDARD,
            "remediation":
                EXPECTED_REMEDIATION,
        }

        for name, count in (
            expected.items()
        ):
            if (
                len(
                    partitions[name]
                )
                != count
            ):
                raise AccessionCentricExecutorError(
                    "POPULATION_COUNT_MISMATCH:"
                    + name
                    + ":"
                    + str(
                        len(
                            partitions[name]
                        )
                    )
                    + ":EXPECTED:"
                    + str(count)
                )

        if (
            len(identities)
            != EXPECTED_GOVERNED_POPULATION
        ):
            raise AccessionCentricExecutorError(
                "GOVERNED_POPULATION_MISMATCH"
            )

    return identities


def build_unresolved_by_cik(
    identities: dict[
        str,
        dict[str, Any],
    ],
    unresolved_security_ids: Iterable[str],
) -> dict[
    str,
    list[dict[str, Any]],
]:
    result: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for security_id in (
        unresolved_security_ids
    ):
        security_id = str(
            security_id
        )

        if security_id not in identities:
            raise AccessionCentricExecutorError(
                "UNRESOLVED_SECURITY_ID_UNKNOWN:"
                + security_id
            )

        identity = identities[
            security_id
        ]

        result[
            _normalize_cik(
                identity[
                    "sec_cik"
                ]
            )
        ].append(
            identity
        )

    for cik in result:
        result[cik].sort(
            key=lambda value: (
                str(
                    value[
                        "security_id"
                    ]
                )
            )
        )

    return dict(result)


def validate_wave_rows(
    rows: Iterable[dict[str, Any]],
    *,
    allowed_ciks: set[str],
) -> list[dict[str, Any]]:
    output = []

    seen_keys = set()

    for raw in rows:
        row = dict(raw)

        cik = _normalize_cik(
            row.get("sec_cik")
        )

        if cik not in allowed_ciks:
            raise AccessionCentricExecutorError(
                "WAVE_CIK_OUTSIDE_UNRESOLVED_SCOPE:"
                + cik
            )

        accession = str(
            row.get(
                "accession_number"
            )
            or ""
        ).strip()

        primary_document = str(
            row.get(
                "primary_document"
            )
            or ""
        ).strip()

        if (
            not accession
            or not primary_document
        ):
            raise AccessionCentricExecutorError(
                "ACCESSION_AND_DOCUMENT_REQUIRED"
            )

        url = filing_document_url(
            cik,
            accession,
            primary_document,
        )

        key = (
            cik,
            accession,
            primary_document,
            url,
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)

        row["sec_cik"] = cik
        row["source_url"] = url

        output.append(row)

    return output


def evaluate_accession_payload(
    *,
    sec_cik: str,
    identities: Iterable[
        dict[str, Any]
    ],
    payload: bytes,
) -> dict[
    str,
    dict[str, Any],
]:
    cik = _normalize_cik(
        sec_cik
    )

    output = {}

    for raw in identities:
        identity = validate_identity(
            raw
        )

        if (
            _normalize_cik(
                identity["sec_cik"]
            )
            != cik
        ):
            raise AccessionCentricExecutorError(
                "CROSS_CIK_IDENTITY_EVALUATION_BLOCKED:"
                + str(
                    identity[
                        "security_id"
                    ]
                )
            )

        security_id = str(
            identity[
                "security_id"
            ]
        )

        output[
            security_id
        ] = evaluate_candidate(
            identity,
            payload,
        )

    return output


def _checkpoint_map_sha256(
    value: dict[str, Any],
) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode(
        "utf-8"
    )

    return sha256_bytes(
        payload
    )


def _load_checkpoint(
    checkpoint_path: Path,
    *,
    wave_plan_sha256: str,
    wave_membership_sha256: str,
) -> dict[str, Any]:
    if not checkpoint_path.exists():
        return {
            "artifact_id":
                CHECKPOINT_ARTIFACT_ID,
            "execution_model":
                EXECUTION_MODEL,
            "wave_plan_sha256":
                wave_plan_sha256,
            "wave_membership_sha256":
                wave_membership_sha256,
            "completed":
                {},
            "security_outcomes":
                {},
        }

    checkpoint = load_json(
        checkpoint_path
    )

    if (
        checkpoint.get(
            "artifact_id"
        )
        != CHECKPOINT_ARTIFACT_ID
    ):
        raise AccessionCentricExecutorError(
            "CHECKPOINT_ARTIFACT_MISMATCH"
        )

    if (
        checkpoint.get(
            "execution_model"
        )
        != EXECUTION_MODEL
    ):
        raise AccessionCentricExecutorError(
            "CHECKPOINT_EXECUTION_MODEL_MISMATCH"
        )

    if (
        checkpoint.get(
            "wave_plan_sha256"
        )
        != wave_plan_sha256
    ):
        raise AccessionCentricExecutorError(
            "CHECKPOINT_WAVE_PLAN_SHA_MISMATCH"
        )

    if (
        checkpoint.get(
            "wave_membership_sha256"
        )
        != wave_membership_sha256
    ):
        raise AccessionCentricExecutorError(
            "CHECKPOINT_WAVE_MEMBERSHIP_SHA_MISMATCH"
        )

    if not isinstance(
        checkpoint.get(
            "completed"
        ),
        dict,
    ):
        raise AccessionCentricExecutorError(
            "CHECKPOINT_COMPLETED_OBJECT_REQUIRED"
        )

    if (
        "security_outcomes"
        not in checkpoint
    ):
        checkpoint[
            "security_outcomes"
        ] = {}

    if not isinstance(
        checkpoint.get(
            "security_outcomes"
        ),
        dict,
    ):
        raise AccessionCentricExecutorError(
            "CHECKPOINT_SECURITY_OUTCOMES_OBJECT_REQUIRED"
        )

    security_outcomes = checkpoint[
        "security_outcomes"
    ]

    recorded_outcome_sha = (
        checkpoint.get(
            "security_outcomes_sha256"
        )
    )

    if security_outcomes:
        if not isinstance(
            recorded_outcome_sha,
            str,
        ) or not recorded_outcome_sha:
            raise AccessionCentricExecutorError(
                "CHECKPOINT_SECURITY_OUTCOMES_SHA_REQUIRED"
            )

        actual_outcome_sha = (
            _checkpoint_map_sha256(
                security_outcomes
            )
        )

        if (
            actual_outcome_sha
            != recorded_outcome_sha
        ):
            raise AccessionCentricExecutorError(
                "CHECKPOINT_SECURITY_OUTCOMES_HASH_MISMATCH"
            )

    elif recorded_outcome_sha is not None:
        actual_outcome_sha = (
            _checkpoint_map_sha256(
                security_outcomes
            )
        )

        if (
            actual_outcome_sha
            != recorded_outcome_sha
        ):
            raise AccessionCentricExecutorError(
                "CHECKPOINT_SECURITY_OUTCOMES_HASH_MISMATCH"
            )

    return checkpoint


def _find_existing_raw(
    *,
    cache_roots: Iterable[
        str | Path
    ],
    cik: str,
    accession: str,
    primary_document: str,
) -> Path | None:
    flat = accession.replace(
        "-",
        "",
    )

    for root_value in cache_roots:
        root = Path(
            root_value
        )

        legacy = (
            root
            / "sec_taxonomy"
            / "filings"
            / f"CIK{cik}"
            / flat
            / primary_document
        )

        if legacy.is_file():
            return legacy

        content_root = (
            root
            / "sec_taxonomy"
            / "accession_documents"
            / f"CIK{cik}"
            / flat
        )

        if (
            content_root.is_dir()
        ):
            matches = sorted(
                content_root.glob(
                    "*/" + primary_document
                )
            )

            if matches:
                return matches[0]

    return None


def _write_content_addressed_document(
    *,
    raw_root: str | Path,
    cik: str,
    accession: str,
    primary_document: str,
    payload: bytes,
) -> Path:
    content_sha = sha256_bytes(
        payload
    )

    flat = accession.replace(
        "-",
        "",
    )

    target = (
        Path(raw_root)
        / "sec_taxonomy"
        / "accession_documents"
        / f"CIK{cik}"
        / flat
        / content_sha
        / primary_document
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if target.exists():
        existing = target.read_bytes()

        if (
            sha256_bytes(existing)
            != content_sha
        ):
            raise AccessionCentricExecutorError(
                "CONTENT_ADDRESSED_RAW_COLLISION:"
                + str(target)
            )

        return target

    temporary = target.with_suffix(
        target.suffix + ".tmp"
    )

    temporary.write_bytes(
        payload
    )

    os.replace(
        temporary,
        target,
    )

    return target


def execute_accession_wave(
    *,
    wave_rows: Iterable[
        dict[str, Any]
    ],
    all_identities: Iterable[
        dict[str, Any]
    ],
    unresolved_security_ids: Iterable[str],
    resolved_security_ids: Iterable[str],
    conflicted_security_ids: Iterable[str],
    remediation_security_ids: Iterable[str],
    wave_plan_sha256: str,
    wave_membership_sha256: str,
    raw_root: str | Path,
    checkpoint_path: str | Path,
    cache_roots: Iterable[
        str | Path
    ] = (),
    maximum_unique_document_requests: int,
    maximum_requests_per_second: float,
    request_timeout_seconds: int,
    user_agent: str,
    network_capture_authorized: bool,
    fetcher: FetchFunction | None,
    sleeper: Callable[
        [float],
        None,
    ] = time.sleep,
    enforce_production_counts: bool = True,
) -> dict[str, Any]:
    identities = (
        validate_population_partition(
            all_identities=
                all_identities,
            unresolved_security_ids=
                unresolved_security_ids,
            resolved_security_ids=
                resolved_security_ids,
            conflicted_security_ids=
                conflicted_security_ids,
            remediation_security_ids=
                remediation_security_ids,
            enforce_production_counts=
                enforce_production_counts,
        )
    )

    unresolved_ids = set(
        str(value)
        for value
        in unresolved_security_ids
    )

    resolved_ids = set(
        str(value)
        for value
        in resolved_security_ids
    )

    conflicted_ids = set(
        str(value)
        for value
        in conflicted_security_ids
    )

    remediation_ids = set(
        str(value)
        for value
        in remediation_security_ids
    )

    unresolved_by_cik = (
        build_unresolved_by_cik(
            identities,
            unresolved_ids,
        )
    )

    rows = validate_wave_rows(
        wave_rows,
        allowed_ciks=set(
            unresolved_by_cik
        ),
    )

    if (
        maximum_unique_document_requests
        < 0
    ):
        raise AccessionCentricExecutorError(
            "INVALID_REQUEST_CEILING"
        )

    if (
        maximum_requests_per_second
        <= 0
    ):
        raise AccessionCentricExecutorError(
            "INVALID_REQUEST_RATE"
        )

    if request_timeout_seconds <= 0:
        raise AccessionCentricExecutorError(
            "INVALID_REQUEST_TIMEOUT"
        )

    if (
        network_capture_authorized
        and fetcher is None
    ):
        raise AccessionCentricExecutorError(
            "EXPLICIT_FETCHER_REQUIRED"
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
        raise AccessionCentricExecutorError(
            "IDENTIFYING_SEC_USER_AGENT_REQUIRED"
        )

    checkpoint_target = Path(
        checkpoint_path
    )

    checkpoint = _load_checkpoint(
        checkpoint_target,
        wave_plan_sha256=
            wave_plan_sha256,
        wave_membership_sha256=
            wave_membership_sha256,
    )

    completed = checkpoint[
        "completed"
    ]

    current_run_requests = 0

    evaluations_by_security: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    accession_records = []

    for row in rows:
        cik = row[
            "sec_cik"
        ]

        accession = str(
            row[
                "accession_number"
            ]
        )

        primary_document = str(
            row[
                "primary_document"
            ]
        )

        url = str(
            row[
                "source_url"
            ]
        )

        existing = completed.get(
            url
        )

        payload: bytes
        raw_path: Path
        reused = False
        resume_reused = False
        network_requested = False

        if existing is not None:
            raw_path = Path(
                existing[
                    "raw_path"
                ]
            )

            if not raw_path.is_file():
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_RAW_FILE_MISSING:"
                    + str(raw_path)
                )

            payload = raw_path.read_bytes()

            content_sha = (
                sha256_bytes(
                    payload
                )
            )

            if (
                content_sha
                != existing[
                    "content_sha256"
                ]
            ):
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_RAW_HASH_MISMATCH:"
                    + url
                )

            resume_reused = True

            status = int(
                existing[
                    "http_status"
                ]
            )

            final_url = str(
                existing[
                    "final_url"
                ]
            )

        else:
            cached = _find_existing_raw(
                cache_roots=(
                    tuple(cache_roots)
                    + (
                        raw_root,
                    )
                ),
                cik=cik,
                accession=accession,
                primary_document=
                    primary_document,
            )

            if cached is not None:
                payload = (
                    cached.read_bytes()
                )

                if not payload:
                    raise AccessionCentricExecutorError(
                        "CACHED_DOCUMENT_EMPTY:"
                        + str(cached)
                    )

                raw_path = cached
                reused = True
                status = 200
                final_url = url

            else:
                if (
                    not
                    network_capture_authorized
                ):
                    raise AccessionCentricExecutorError(
                        "NETWORK_CAPTURE_NOT_AUTHORIZED:"
                        + url
                    )

                if fetcher is None:
                    raise AccessionCentricExecutorError(
                        "EXPLICIT_FETCHER_REQUIRED"
                    )

                if (
                    current_run_requests
                    >= maximum_unique_document_requests
                ):
                    raise AccessionCentricExecutorError(
                        "DOCUMENT_REQUEST_CEILING_EXHAUSTED"
                    )

                if (
                    current_run_requests
                    > 0
                ):
                    sleeper(
                        1.0
                        / maximum_requests_per_second
                    )

                (
                    status,
                    final_url,
                    payload,
                ) = fetcher(
                    url,
                    user_agent.strip(),
                    request_timeout_seconds,
                )

                current_run_requests += 1
                network_requested = True

                if int(status) != 200:
                    raise AccessionCentricExecutorError(
                        "SEC_HTTP_STATUS:"
                        + str(status)
                        + ":"
                        + url
                    )

                if not payload:
                    raise AccessionCentricExecutorError(
                        "EMPTY_DOCUMENT_PAYLOAD:"
                        + url
                    )

                raw_path = (
                    _write_content_addressed_document(
                        raw_root=raw_root,
                        cik=cik,
                        accession=accession,
                        primary_document=
                            primary_document,
                        payload=payload,
                    )
                )

            content_sha = sha256_bytes(
                payload
            )

            completed[url] = {
                "sec_cik":
                    cik,
                "accession_number":
                    accession,
                "primary_document":
                    primary_document,
                "source_url":
                    url,
                "http_status":
                    int(status),
                "final_url":
                    str(final_url),
                "content_sha256":
                    content_sha,
                "byte_count":
                    len(payload),
                "raw_path":
                    str(raw_path),
                "cache_reused":
                    bool(reused),
                "network_requested":
                    bool(
                        network_requested
                    ),
            }

        completed_entry = completed[
            url
        ]

        stored_evaluations = (
            completed_entry.get(
                "evaluations"
            )
        )

        expected_security_ids = {
            str(
                identity[
                    "security_id"
                ]
            )
            for identity
            in unresolved_by_cik[
                cik
            ]
        }

        if stored_evaluations is not None:
            if not isinstance(
                stored_evaluations,
                dict,
            ):
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_EVALUATIONS_OBJECT_REQUIRED:"
                    + url
                )

            recorded_evaluations_sha = (
                completed_entry.get(
                    "evaluations_sha256"
                )
            )

            if not isinstance(
                recorded_evaluations_sha,
                str,
            ) or not recorded_evaluations_sha:
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_EVALUATIONS_SHA_REQUIRED:"
                    + url
                )

            actual_evaluations_sha = (
                _checkpoint_map_sha256(
                    stored_evaluations
                )
            )

            if (
                actual_evaluations_sha
                != recorded_evaluations_sha
            ):
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_EVALUATIONS_HASH_MISMATCH:"
                    + url
                )

            if (
                set(
                    str(value)
                    for value
                    in stored_evaluations
                )
                != expected_security_ids
            ):
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_EVALUATION_SECURITY_SET_MISMATCH:"
                    + url
                )

            candidate_by_security = {}

            for security_id in sorted(
                expected_security_ids
            ):
                candidate = (
                    stored_evaluations[
                        security_id
                    ]
                )

                if not isinstance(
                    candidate,
                    dict,
                ):
                    raise AccessionCentricExecutorError(
                        "CHECKPOINT_EVALUATION_RECORD_REQUIRED:"
                        + security_id
                    )

                if (
                    _normalize_cik(
                        candidate.get(
                            "sec_cik"
                        )
                    )
                    != cik
                ):
                    raise AccessionCentricExecutorError(
                        "CHECKPOINT_EVALUATION_CIK_MISMATCH:"
                        + security_id
                    )

                expected_fields = {
                    "accession_number":
                        accession,
                    "primary_document":
                        primary_document,
                    "source_url":
                        url,
                    "final_url":
                        str(final_url),
                    "content_sha256":
                        content_sha,
                    "raw_path":
                        str(raw_path),
                }

                for (
                    field,
                    expected_value,
                ) in expected_fields.items():
                    if (
                        str(
                            candidate.get(
                                field
                            )
                        )
                        != str(
                            expected_value
                        )
                    ):
                        raise AccessionCentricExecutorError(
                            "CHECKPOINT_EVALUATION_PROVENANCE_MISMATCH:"
                            + security_id
                            + ":"
                            + field
                        )

                if (
                    int(
                        candidate.get(
                            "http_status"
                        )
                    )
                    != int(status)
                ):
                    raise AccessionCentricExecutorError(
                        "CHECKPOINT_EVALUATION_HTTP_STATUS_MISMATCH:"
                        + security_id
                    )

                candidate_by_security[
                    security_id
                ] = dict(
                    candidate
                )

            matching_security_ids = sorted(
                security_id
                for (
                    security_id,
                    candidate,
                ) in candidate_by_security.items()
                if candidate.get(
                    "product_specific"
                )
                is True
            )

            recorded_matching_ids = (
                completed_entry.get(
                    "matching_security_ids"
                )
            )

            if (
                recorded_matching_ids
                is not None
                and sorted(
                    str(value)
                    for value
                    in recorded_matching_ids
                )
                != matching_security_ids
            ):
                raise AccessionCentricExecutorError(
                    "CHECKPOINT_MATCHING_SECURITY_IDS_MISMATCH:"
                    + url
                )

        else:
            evaluations = (
                evaluate_accession_payload(
                    sec_cik=cik,
                    identities=
                        unresolved_by_cik[
                            cik
                        ],
                    payload=payload,
                )
            )

            candidate_by_security = {}

            matching_security_ids = []

            for (
                security_id,
                evaluation,
            ) in evaluations.items():
                candidate = {
                    "sec_cik":
                        cik,
                    "accession_number":
                        accession,
                    "primary_document":
                        primary_document,
                    "form":
                        row.get("form"),
                    "filing_date":
                        row.get(
                            "filing_date"
                        ),
                    "source_url":
                        url,
                    "final_url":
                        str(final_url),
                    "http_status":
                        int(status),
                    "content_sha256":
                        content_sha,
                    "raw_path":
                        str(raw_path),
                    **evaluation,
                }

                candidate_by_security[
                    security_id
                ] = candidate

                if (
                    evaluation.get(
                        "product_specific"
                    )
                    is True
                ):
                    matching_security_ids.append(
                        security_id
                    )

            if (
                set(
                    candidate_by_security
                )
                != expected_security_ids
            ):
                raise AccessionCentricExecutorError(
                    "EVALUATION_SECURITY_SET_MISMATCH:"
                    + url
                )

            completed_entry[
                "evaluations"
            ] = candidate_by_security

            completed_entry[
                "evaluations_sha256"
            ] = _checkpoint_map_sha256(
                candidate_by_security
            )

            completed_entry[
                "evaluated_identity_count"
            ] = len(
                expected_security_ids
            )

            completed_entry[
                "matching_security_ids"
            ] = sorted(
                matching_security_ids
            )

            _atomic_write_json(
                checkpoint_target,
                checkpoint,
            )

        for (
            security_id,
            candidate,
        ) in candidate_by_security.items():
            evaluations_by_security[
                security_id
            ].append(
                dict(candidate)
            )

        accession_records.append(
            {
                "sec_cik":
                    cik,
                "accession_number":
                    accession,
                "primary_document":
                    primary_document,
                "source_url":
                    url,
                "content_sha256":
                    content_sha,
                "raw_path":
                    str(raw_path),
                "network_requested":
                    network_requested,
                "cache_reused":
                    reused,
                "resume_reused":
                    resume_reused,
                "evaluated_identity_count":
                    len(
                        expected_security_ids
                    ),
                "matching_security_ids":
                    sorted(
                        matching_security_ids
                    ),
            }
        )

    unresolved_records = []

    for security_id in sorted(
        unresolved_ids
    ):
        identity = identities[
            security_id
        ]

        candidates = list(
            evaluations_by_security.get(
                security_id,
                [],
            )
        )

        resolution = (
            choose_resolution(
                identity,
                candidates,
            )
        )

        unresolved_records.append(
            {
                "security_id":
                    security_id,
                "symbol":
                    identity[
                        "symbol"
                    ],
                "sec_cik":
                    identity[
                        "sec_cik"
                    ],
                "sec_series_id":
                    identity[
                        "sec_series_id"
                    ],
                "sec_class_contract_id":
                    identity[
                        "sec_class_contract_id"
                    ],
                "review_state":
                    resolution[
                        "review_state"
                    ],
                "evaluated_candidate_count":
                    len(candidates),
                "product_specific_candidate_count":
                    sum(
                        1
                        for candidate
                        in candidates
                        if candidate.get(
                            "product_specific"
                        )
                        is True
                    ),
                "resolution":
                    resolution,
                "taxonomy_dimensions_assigned":
                    False,
            }
        )

    security_outcomes = {
        str(
            record[
                "security_id"
            ]
        ):
            record
        for record
        in unresolved_records
    }

    checkpoint[
        "security_outcomes"
    ] = security_outcomes

    checkpoint[
        "security_outcomes_sha256"
    ] = _checkpoint_map_sha256(
        security_outcomes
    )

    _atomic_write_json(
        checkpoint_target,
        checkpoint,
    )

    return {
        "artifact_id":
            "ETF_849_ACCESSION_CENTRIC_DOCUMENT_EXECUTION_RESULT",
        "execution_model":
            EXECUTION_MODEL,
        "governed_population_count":
            len(identities),
        "unresolved_standard_input_count":
            len(unresolved_ids),
        "preserved_resolved_standard_count":
            len(resolved_ids),
        "preserved_conflicted_standard_count":
            len(conflicted_ids),
        "preserved_remediation_count":
            len(remediation_ids),
        "wave_accession_document_count":
            len(rows),
        "current_run_document_requests":
            current_run_requests,
        "accession_records":
            accession_records,
        "unresolved_records":
            unresolved_records,
        "taxonomy_classification_performed":
            0,
        "taxonomy_normalization_performed":
            0,
        "ranking_performed":
            0,
        "recommendations_performed":
            0,
        "allocation_performed":
            0,
        "automatic_execution_performed":
            0,
        "uip_database_writes_performed":
            0,
    }
