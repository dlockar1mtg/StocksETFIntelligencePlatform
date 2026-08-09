from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from foundation.market.authoritative_etf_taxonomy_sec_executor import (
    AuthoritativeTaxonomySECExecutorError,
    build_request_plan,
    execute_authorized_capture,
)

from foundation.market.sec_historical_series_class_header_capture import (
    fetch_once,
)


EXPECTED_POPULATION = 1077
EXPECTED_STANDARD_GROUPS = 102
EXPECTED_STANDARD_ETFS = 862
EXPECTED_REMEDIATION_GROUPS = 1
EXPECTED_REMEDIATION_ETFS = 215

EXPECTED_IDENTITY_MANIFEST_SHA = (
    "9ed50f6e8ac414d347cb563a651067326"
    "31ec5a4c1c092142411900e19d03520"
)

EXPECTED_AUTHORIZATION_ID = (
    "ETF_1077_AUTHORITATIVE_SEC_CAPTURE_AUTHORIZATION_V1"
)


class ProductionSECCaptureLaunchError(RuntimeError):
    pass


FetchFunction = Callable[
    [str, str, int],
    tuple[int, str, bytes],
]


def sha256_path(path: str | Path) -> str:
    return hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()


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
        raise ProductionSECCaptureLaunchError(
            "JSON object required."
        )

    return value


def validate_authorization(
    authorization: dict[str, Any],
    *,
    identity_manifest_sha256: str,
    require_live_execution: bool,
) -> dict[str, Any]:

    if (
        authorization.get(
            "authorization_id"
        )
        != EXPECTED_AUTHORIZATION_ID
    ):
        raise ProductionSECCaptureLaunchError(
            "Authorization ID mismatch."
        )

    if (
        authorization.get(
            "authorization_version"
        )
        != "1.0.0"
    ):
        raise ProductionSECCaptureLaunchError(
            "Authorization version mismatch."
        )

    if (
        int(
            authorization.get(
                "governed_population",
                -1,
            )
        )
        != EXPECTED_POPULATION
    ):
        raise ProductionSECCaptureLaunchError(
            "Authorization population mismatch."
        )

    if (
        authorization.get(
            "identity_bound_manifest_sha256"
        )
        != identity_manifest_sha256
    ):
        raise ProductionSECCaptureLaunchError(
            "Authorization manifest SHA mismatch."
        )

    if (
        identity_manifest_sha256
        != EXPECTED_IDENTITY_MANIFEST_SHA
    ):
        raise ProductionSECCaptureLaunchError(
            "Identity manifest is not the frozen production contract."
        )

    expected_counts = {
        "standard_registrant_count":
            EXPECTED_STANDARD_GROUPS,

        "standard_etf_count":
            EXPECTED_STANDARD_ETFS,

        "remediation_registrant_count":
            EXPECTED_REMEDIATION_GROUPS,

        "remediation_etf_count":
            EXPECTED_REMEDIATION_ETFS,
    }

    for field, expected in (
        expected_counts.items()
    ):
        if int(
            authorization.get(
                field,
                -1,
            )
        ) != expected:
            raise ProductionSECCaptureLaunchError(
                f"Authorization count drift: {field}"
            )

    standard = authorization.get(
        "standard_route"
    )

    remediation = authorization.get(
        "remediation_route"
    )

    downstream = authorization.get(
        "downstream_authority"
    )

    if not isinstance(
        standard,
        dict,
    ):
        raise ProductionSECCaptureLaunchError(
            "Standard-route authorization block missing."
        )

    if not isinstance(
        remediation,
        dict,
    ):
        raise ProductionSECCaptureLaunchError(
            "Remediation authorization block missing."
        )

    if not isinstance(
        downstream,
        dict,
    ):
        raise ProductionSECCaptureLaunchError(
            "Downstream authority block missing."
        )

    if (
        int(
            standard.get(
                "maximum_submission_requests",
                -1,
            )
        )
        != EXPECTED_STANDARD_GROUPS
    ):
        raise ProductionSECCaptureLaunchError(
            "Submission request ceiling mismatch."
        )

    if (
        int(
            standard.get(
                "maximum_candidate_filings_per_security",
                -1,
            )
        )
        != 5
    ):
        raise ProductionSECCaptureLaunchError(
            "Candidate filing ceiling mismatch."
        )

    if (
        int(
            standard.get(
                "maximum_candidate_document_requests",
                -1,
            )
        )
        != 4310
    ):
        raise ProductionSECCaptureLaunchError(
            "Document request ceiling mismatch."
        )

    if (
        int(
            standard.get(
                "maximum_unique_sec_requests",
                -1,
            )
        )
        != 4412
    ):
        raise ProductionSECCaptureLaunchError(
            "Total SEC request ceiling mismatch."
        )

    rate = float(
        standard.get(
            "maximum_requests_per_second",
            0,
        )
    )

    if (
        rate <= 0
        or rate > 10
    ):
        raise ProductionSECCaptureLaunchError(
            "Invalid SEC request-rate ceiling."
        )

    if (
        int(
            standard.get(
                "request_timeout_seconds",
                0,
            )
        )
        < 1
    ):
        raise ProductionSECCaptureLaunchError(
            "Invalid SEC request timeout."
        )

    for required_true in (
        "cache_identical_requests",
        "immutable_raw_storage",
        "content_addressed_submissions_storage",
    ):
        if (
            standard.get(
                required_true
            )
            is not True
        ):
            raise ProductionSECCaptureLaunchError(
                f"Required control disabled: {required_true}"
            )

    if (
        remediation.get(
            "standard_route_execution_authorized"
        )
        is not False
    ):
        raise ProductionSECCaptureLaunchError(
            "Remediation standard route must remain disabled."
        )

    if (
        remediation.get(
            "delegated_executor"
        )
        != "EXISTING_SERIES_CLASS_REMEDIATION_ARCHITECTURE"
    ):
        raise ProductionSECCaptureLaunchError(
            "Remediation executor mismatch."
        )

    if (
        int(
            remediation.get(
                "member_count",
                -1,
            )
        )
        != EXPECTED_REMEDIATION_ETFS
    ):
        raise ProductionSECCaptureLaunchError(
            "Remediation population mismatch."
        )

    for prohibited in (
        "production_taxonomy_classification_authorized",
        "taxonomy_normalization_authorized",
        "production_taxonomy_certification_authorized",
        "ranking_authorized",
        "recommendations_authorized",
        "portfolio_allocation_authorized",
        "automatic_execution_authorized",
    ):
        if (
            downstream.get(
                prohibited
            )
            is not False
        ):
            raise ProductionSECCaptureLaunchError(
                f"Downstream authority unexpectedly open: {prohibited}"
            )

    if require_live_execution:
        if (
            authorization.get(
                "production_execution_authorized"
            )
            is not True
        ):
            raise ProductionSECCaptureLaunchError(
                "Production execution is not authorized."
            )

        if (
            standard.get(
                "network_capture_authorized"
            )
            is not True
        ):
            raise ProductionSECCaptureLaunchError(
                "Network capture is not authorized."
            )

        if (
            standard.get(
                "authoritative_source_capture_authorized"
            )
            is not True
        ):
            raise ProductionSECCaptureLaunchError(
                "Source capture is not authorized."
            )

    return standard


def validate_policy_for_launch(
    policy: dict[str, Any],
    *,
    require_live_execution: bool,
) -> None:

    if (
        int(
            policy.get(
                "required_record_count",
                -1,
            )
        )
        != EXPECTED_POPULATION
    ):
        raise ProductionSECCaptureLaunchError(
            "Acquisition-policy population mismatch."
        )

    authority = policy.get(
        "authority"
    )

    if not isinstance(
        authority,
        dict,
    ):
        raise ProductionSECCaptureLaunchError(
            "Acquisition-policy authority block missing."
        )

    for prohibited in (
        "production_taxonomy_classification",
        "production_taxonomy_certification",
        "benchmark_qualified_universe_publication",
        "relative_return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    ):
        if (
            authority.get(
                prohibited
            )
            is not False
        ):
            raise ProductionSECCaptureLaunchError(
                f"Policy downstream authority unexpectedly open: {prohibited}"
            )

    if require_live_execution:
        if (
            policy.get(
                "policy_version"
            )
            != "1.2.0"
        ):
            raise ProductionSECCaptureLaunchError(
                "Live production requires acquisition policy 1.2.0."
            )

        if (
            authority.get(
                "authoritative_source_capture"
            )
            is not True
        ):
            raise ProductionSECCaptureLaunchError(
                "Acquisition policy has not authorized source capture."
            )

    else:
        if (
            policy.get(
                "policy_version"
            )
            != "1.1.0"
        ):
            raise ProductionSECCaptureLaunchError(
                "Offline certification expects current policy 1.1.0."
            )

        if (
            authority.get(
                "authoritative_source_capture"
            )
            is not False
        ):
            raise ProductionSECCaptureLaunchError(
                "Offline certification requires source capture closed."
            )


def build_launch_plan(
    contract: dict[str, Any],
    policy: dict[str, Any],
    authorization: dict[str, Any],
    *,
    identity_manifest_sha256: str,
) -> dict[str, Any]:

    validate_policy_for_launch(
        policy,
        require_live_execution=False,
    )

    standard = validate_authorization(
        authorization,
        identity_manifest_sha256=
            identity_manifest_sha256,
        require_live_execution=False,
    )

    request_plan = build_request_plan(
        contract
    )

    if (
        request_plan[
            "unique_submission_request_count"
        ]
        != EXPECTED_STANDARD_GROUPS
    ):
        raise ProductionSECCaptureLaunchError(
            "Production request-plan drift."
        )

    return {
        "artifact_id":
            "ETF_1077_AUTHORITATIVE_SEC_CAPTURE_LAUNCH_PLAN",

        "governed_population":
            EXPECTED_POPULATION,

        "standard_registrant_count":
            EXPECTED_STANDARD_GROUPS,

        "standard_etf_count":
            EXPECTED_STANDARD_ETFS,

        "remediation_registrant_count":
            EXPECTED_REMEDIATION_GROUPS,

        "remediation_etf_count":
            EXPECTED_REMEDIATION_ETFS,

        "initial_submission_requests":
            request_plan[
                "unique_submission_request_count"
            ],

        "maximum_unique_sec_requests":
            int(
                standard[
                    "maximum_unique_sec_requests"
                ]
            ),

        "maximum_requests_per_second":
            float(
                standard[
                    "maximum_requests_per_second"
                ]
            ),

        "production_execution_authorized":
            False,

        "network_requests_performed":
            0,

        "sec_requests_performed":
            0,

        "next_required_step":
            "VERSION_AND_AUTHORIZE_ACQUISITION_POLICY_FOR_PRODUCTION_CAPTURE",
    }


def execute_live(
    contract: dict[str, Any],
    policy: dict[str, Any],
    authorization: dict[str, Any],
    *,
    identity_manifest_sha256: str,
    user_agent: str,
    raw_root: str | Path,
    fetcher: FetchFunction = fetch_once,
) -> dict[str, Any]:

    validate_policy_for_launch(
        policy,
        require_live_execution=True,
    )

    standard = validate_authorization(
        authorization,
        identity_manifest_sha256=
            identity_manifest_sha256,
        require_live_execution=True,
    )

    executor_authorization = {
        "network_capture_authorized":
            True,

        "authoritative_source_capture_authorized":
            True,

        "identity_bound_manifest_sha256":
            identity_manifest_sha256,

        "maximum_unique_sec_requests":
            int(
                standard[
                    "maximum_unique_sec_requests"
                ]
            ),

        "maximum_requests_per_second":
            float(
                standard[
                    "maximum_requests_per_second"
                ]
            ),

        "maximum_candidate_filings_per_security":
            int(
                standard[
                    "maximum_candidate_filings_per_security"
                ]
            ),

        "request_timeout_seconds":
            int(
                standard[
                    "request_timeout_seconds"
                ]
            ),

        "production_taxonomy_classification_authorized":
            False,

        "taxonomy_normalization_authorized":
            False,
    }

    try:
        return execute_authorized_capture(
            contract,
            policy,
            executor_authorization,
            manifest_sha256=
                identity_manifest_sha256,
            user_agent=
                user_agent,
            raw_root=
                raw_root,
            fetcher=
                fetcher,
        )

    except AuthoritativeTaxonomySECExecutorError:
        raise
