from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from foundation.infrastructure.sec_fund_tickers import write_immutable
from foundation.market.sec_series_class_specific_filing_resolution import (
    choose_resolution,
    evaluate_candidate,
    iter_candidate_filings,
)


EXPECTED_POPULATION = 1077
EXPECTED_GROUP_COUNT = 103

EXPECTED_STANDARD_GROUPS = 102
EXPECTED_STANDARD_ETFS = 862

EXPECTED_REMEDIATION_GROUPS = 1
EXPECTED_REMEDIATION_ETFS = 215

STANDARD_LANE = "STANDARD_REGISTRANT_AUTHORITY_ACQUISITION"
REMEDIATION_LANE = "GOVERNED_EXISTING_REMEDIATION_ROUTE"

ALLOWED_FORMS = (
    "N-1A",
    "N-1A/A",
    "497",
    "497K",
    "485APOS",
    "485BPOS",
)


class AuthoritativeTaxonomySECExecutorError(RuntimeError):
    """Raised when governed SEC execution cannot proceed safely."""


FetchFunction = Callable[
    [str, str, int],
    tuple[int, str, bytes],
]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_cik(value: Any) -> str:
    raw = str(value or "").strip()

    if raw.lower().startswith("sec-cik-"):
        raw = raw[8:]

    if not raw.isdigit():
        raise AuthoritativeTaxonomySECExecutorError(
            f"Invalid SEC CIK: {value}"
        )

    return raw.zfill(10)


def _cik_unpadded(value: Any) -> str:
    value = _normalize_cik(value)
    return value.lstrip("0") or "0"


def issuer_key_for_cik(cik: Any) -> str:
    """
    Evidence-backed legal registrant routing identity.

    This must not be interpreted as a commercial fund-family identity.
    """
    return (
        "SEC-REGISTRANT-CIK-"
        + _normalize_cik(cik)
    )


def submissions_url(cik: Any) -> str:
    return (
        "https://data.sec.gov/submissions/"
        f"CIK{_normalize_cik(cik)}.json"
    )


def filing_document_url(
    cik: Any,
    accession_number: str,
    primary_document: str,
) -> str:
    accession = str(
        accession_number or ""
    ).strip()

    document = str(
        primary_document or ""
    ).strip()

    if not accession or not document:
        raise AuthoritativeTaxonomySECExecutorError(
            "Accession number and primary document are required."
        )

    flat = accession.replace("-", "")

    if not flat.isdigit():
        raise AuthoritativeTaxonomySECExecutorError(
            f"Invalid SEC accession number: {accession}"
        )

    if "/" in document or "\\" in document:
        raise AuthoritativeTaxonomySECExecutorError(
            "Primary document must be a filename."
        )

    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{_cik_unpadded(cik)}/"
        f"{flat}/"
        f"{document}"
    )


def validate_policy(
    policy: dict[str, Any],
) -> None:
    if policy.get("policy_version") not in {
        "1.1.0",
        "1.2.0",
    }:
        raise AuthoritativeTaxonomySECExecutorError(
            "Acquisition policy version must equal 1.1.0 or 1.2.0."
        )

    if (
        int(
            policy.get(
                "required_record_count",
                -1,
            )
        )
        != EXPECTED_POPULATION
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Acquisition policy population must equal 1,077."
        )

    authority = policy.get("authority")

    if not isinstance(authority, dict):
        raise AuthoritativeTaxonomySECExecutorError(
            "Acquisition authority block is required."
        )

    if (
        authority.get(
            "authoritative_evidence_manifest_build"
        )
        is not True
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Evidence-manifest construction must remain authorized."
        )

    for prohibited in (
        "production_taxonomy_classification",
        "production_taxonomy_certification",
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
        if authority.get(prohibited) is not False:
            raise AuthoritativeTaxonomySECExecutorError(
                f"Downstream authority unexpectedly open: {prohibited}"
            )


def validate_identity_contract(
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    if (
        contract.get("artifact_id")
        != "ETF_1077_IDENTITY_BOUND_EXECUTION_MANIFEST"
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Identity-bound execution artifact mismatch."
        )

    summary = contract.get("summary")
    groups = contract.get("execution_groups")

    if not isinstance(summary, dict):
        raise AuthoritativeTaxonomySECExecutorError(
            "Identity-bound summary is required."
        )

    if not isinstance(groups, list):
        raise AuthoritativeTaxonomySECExecutorError(
            "Execution groups are required."
        )

    expected = {
        "governed_population": 1077,
        "registrant_group_count": 103,
        "identity_bound_population": 1077,
        "identity_unbound_population": 0,
        "cik_bound_population": 1077,
        "series_bound_population": 1077,
        "class_contract_bound_population": 1077,
        "standard_registrant_count": 102,
        "standard_etf_count": 862,
        "remediation_registrant_count": 1,
        "remediation_etf_count": 215,
        "cik_mismatch_count": 0,
        "symbol_mismatch_count": 0,
    }

    for field, required in expected.items():
        if int(summary.get(field, -1)) != required:
            raise AuthoritativeTaxonomySECExecutorError(
                f"Identity contract summary drift: {field}"
            )

    if summary.get(
        "live_capture_authorized"
    ) is not False:
        raise AuthoritativeTaxonomySECExecutorError(
            "Identity contract may not self-authorize capture."
        )

    if len(groups) != EXPECTED_GROUP_COUNT:
        raise AuthoritativeTaxonomySECExecutorError(
            "Exactly 103 registrant groups are required."
        )

    security_ids: set[str] = set()
    group_ids: set[str] = set()

    lane_groups = Counter()
    lane_etfs = Counter()

    for group in groups:
        group_id = str(
            group.get("capture_group_id")
            or ""
        ).strip()

        cik = _normalize_cik(
            group.get("sec_cik")
        )

        lane = str(
            group.get("lane")
            or ""
        ).strip()

        identities = group.get(
            "security_identities"
        )

        if not group_id:
            raise AuthoritativeTaxonomySECExecutorError(
                "Capture group ID is required."
            )

        if group_id in group_ids:
            raise AuthoritativeTaxonomySECExecutorError(
                f"Duplicate capture group: {group_id}"
            )

        group_ids.add(group_id)

        if lane not in {
            STANDARD_LANE,
            REMEDIATION_LANE,
        }:
            raise AuthoritativeTaxonomySECExecutorError(
                f"Unknown capture lane: {lane}"
            )

        if (
            group.get(
                "identity_binding_complete"
            )
            is not True
        ):
            raise AuthoritativeTaxonomySECExecutorError(
                f"Identity binding incomplete: {group_id}"
            )

        if not isinstance(
            identities,
            list,
        ):
            raise AuthoritativeTaxonomySECExecutorError(
                f"Security identities missing: {group_id}"
            )

        if len(identities) != int(
            group.get(
                "etf_count",
                -1,
            )
        ):
            raise AuthoritativeTaxonomySECExecutorError(
                f"ETF count mismatch: {group_id}"
            )

        for identity in identities:
            security_id = str(
                identity.get(
                    "security_id"
                )
                or ""
            ).strip()

            symbol = str(
                identity.get("symbol")
                or ""
            ).strip()

            member_cik = _normalize_cik(
                identity.get("sec_cik")
            )

            series = str(
                identity.get(
                    "sec_series_id"
                )
                or ""
            ).strip()

            class_id = str(
                identity.get(
                    "sec_class_contract_id"
                )
                or ""
            ).strip()

            if not all(
                (
                    security_id,
                    symbol,
                    series,
                    class_id,
                )
            ):
                raise AuthoritativeTaxonomySECExecutorError(
                    f"Incomplete ETF identity: {security_id}"
                )

            if member_cik != cik:
                raise AuthoritativeTaxonomySECExecutorError(
                    f"CIK mismatch: {security_id}"
                )

            if security_id in security_ids:
                raise AuthoritativeTaxonomySECExecutorError(
                    f"Duplicate ETF identity: {security_id}"
                )

            security_ids.add(
                security_id
            )

            priority = (
                identity.get(
                    "priority_remediation"
                )
                is True
            )

            if (
                lane == STANDARD_LANE
                and priority
            ):
                raise AuthoritativeTaxonomySECExecutorError(
                    "Priority ETF found in standard lane."
                )

            if (
                lane == REMEDIATION_LANE
                and not priority
            ):
                raise AuthoritativeTaxonomySECExecutorError(
                    "Non-priority ETF found in remediation lane."
                )

        lane_groups[lane] += 1
        lane_etfs[lane] += len(
            identities
        )

    if len(security_ids) != EXPECTED_POPULATION:
        raise AuthoritativeTaxonomySECExecutorError(
            "Identity contract does not preserve all 1,077 ETFs."
        )

    if (
        lane_groups[STANDARD_LANE]
        != EXPECTED_STANDARD_GROUPS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Standard registrant count drift."
        )

    if (
        lane_etfs[STANDARD_LANE]
        != EXPECTED_STANDARD_ETFS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Standard ETF count drift."
        )

    if (
        lane_groups[REMEDIATION_LANE]
        != EXPECTED_REMEDIATION_GROUPS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Remediation registrant count drift."
        )

    if (
        lane_etfs[REMEDIATION_LANE]
        != EXPECTED_REMEDIATION_ETFS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Remediation ETF count drift."
        )

    return groups


def build_request_plan(
    contract: dict[str, Any],
) -> dict[str, Any]:
    """
    Produce the production route plan.

    Only the 102 standard registrants receive generic submissions
    requests. The one 215-ETF remediation registrant is delegated
    to the existing governed remediation architecture.
    """
    groups = validate_identity_contract(
        contract
    )

    network_requests = []
    delegated_groups = []

    for group in sorted(
        groups,
        key=lambda value: int(
            value["execution_order"]
        ),
    ):
        if (
            group["lane"]
            == REMEDIATION_LANE
        ):
            delegated_groups.append(
                {
                    "capture_group_id":
                        group[
                            "capture_group_id"
                        ],
                    "execution_order":
                        group[
                            "execution_order"
                        ],
                    "sec_cik":
                        _normalize_cik(
                            group["sec_cik"]
                        ),
                    "lane":
                        REMEDIATION_LANE,
                    "member_count":
                        len(
                            group[
                                "security_identities"
                            ]
                        ),
                    "executor":
                        "EXISTING_SERIES_CLASS_REMEDIATION_ARCHITECTURE",
                    "network_request_required":
                        False,
                }
            )

            continue

        network_requests.append(
            {
                "capture_group_id":
                    group[
                        "capture_group_id"
                    ],
                "execution_order":
                    group[
                        "execution_order"
                    ],
                "sec_cik":
                    _normalize_cik(
                        group["sec_cik"]
                    ),
                "lane":
                    STANDARD_LANE,
                "submission_url":
                    submissions_url(
                        group["sec_cik"]
                    ),
                "member_count":
                    len(
                        group[
                            "security_identities"
                        ]
                    ),
                "network_request_required":
                    True,
            }
        )

    if len(
        network_requests
    ) != EXPECTED_STANDARD_GROUPS:
        raise AuthoritativeTaxonomySECExecutorError(
            "Expected exactly 102 standard submissions requests."
        )

    if len(
        delegated_groups
    ) != EXPECTED_REMEDIATION_GROUPS:
        raise AuthoritativeTaxonomySECExecutorError(
            "Expected exactly one delegated remediation group."
        )

    if (
        sum(
            item["member_count"]
            for item
            in network_requests
        )
        != EXPECTED_STANDARD_ETFS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Standard request population drift."
        )

    if (
        sum(
            item["member_count"]
            for item
            in delegated_groups
        )
        != EXPECTED_REMEDIATION_ETFS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Delegated remediation population drift."
        )

    return {
        "artifact_id":
            "ETF_1077_SEC_EXECUTOR_REQUEST_PLAN",

        "governed_population":
            EXPECTED_POPULATION,

        "registrant_group_count":
            EXPECTED_GROUP_COUNT,

        "standard_registrant_count":
            EXPECTED_STANDARD_GROUPS,

        "standard_etf_count":
            EXPECTED_STANDARD_ETFS,

        "remediation_registrant_count":
            EXPECTED_REMEDIATION_GROUPS,

        "remediation_etf_count":
            EXPECTED_REMEDIATION_ETFS,

        "unique_submission_request_count":
            len(
                network_requests
            ),

        "network_requests":
            network_requests,

        "delegated_remediation_groups":
            delegated_groups,

        "network_requests_performed":
            0,

        "sec_requests_performed":
            0,
    }


def _validate_authorization(
    authorization: dict[str, Any],
    *,
    manifest_sha256: str,
) -> None:
    if (
        authorization.get(
            "network_capture_authorized"
        )
        is not True
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Network capture authorization is required."
        )

    if (
        authorization.get(
            "authoritative_source_capture_authorized"
        )
        is not True
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Authoritative source capture authorization is required."
        )

    if (
        str(
            authorization.get(
                "identity_bound_manifest_sha256"
            )
            or ""
        )
        != manifest_sha256
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Authorization is not bound to identity manifest."
        )

    if (
        int(
            authorization.get(
                "maximum_unique_sec_requests",
                0,
            )
        )
        < EXPECTED_STANDARD_GROUPS
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Request ceiling cannot cover standard registrants."
        )

    rate = float(
        authorization.get(
            "maximum_requests_per_second",
            0,
        )
    )

    if rate <= 0:
        raise AuthoritativeTaxonomySECExecutorError(
            "Positive SEC request rate is required."
        )

    if rate > 10:
        raise AuthoritativeTaxonomySECExecutorError(
            "SEC request rate may not exceed 10 per second."
        )

    if (
        int(
            authorization.get(
                "maximum_candidate_filings_per_security",
                0,
            )
        )
        < 1
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Candidate filing ceiling must be positive."
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
        raise AuthoritativeTaxonomySECExecutorError(
            "Positive request timeout is required."
        )

    if (
        authorization.get(
            "production_taxonomy_classification_authorized"
        )
        is not False
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Executor may not authorize classification."
        )

    if (
        authorization.get(
            "taxonomy_normalization_authorized"
        )
        is not False
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Executor may not authorize normalization."
        )


def _base_record(
    *,
    member: dict[str, Any],
    group: dict[str, Any],
    cik: str,
) -> dict[str, Any]:
    return {
        "security_id":
            member["security_id"],

        "symbol":
            member["symbol"],

        "acquisition_state":
            "UNRESOLVED",

        "issuer_key":
            issuer_key_for_cik(
                cik
            ),

        "source_tier":
            None,

        "source_id":
            None,

        "source_record_id":
            None,

        "source_url":
            None,

        "content_sha256":
            None,

        "captured_at_utc":
            utc_now(),

        "acquisition_reasons":
            [],

        "taxonomy_dimensions_assigned":
            False,

        "sec_cik":
            cik,

        "sec_series_id":
            member[
                "sec_series_id"
            ],

        "sec_class_contract_id":
            member[
                "sec_class_contract_id"
            ],

        "lane":
            group["lane"],

        "capture_group_id":
            group[
                "capture_group_id"
            ],

        "production_taxonomy_classification_authorized":
            False,

        "taxonomy_normalization_authorized":
            False,
    }


def execute_authorized_capture(
    contract: dict[str, Any],
    policy: dict[str, Any],
    authorization: dict[str, Any],
    *,
    manifest_sha256: str,
    user_agent: str,
    raw_root: str | Path,
    fetcher: FetchFunction,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """
    Execute governed STANDARD SEC source capture.

    The remediation registrant is explicitly delegated and never
    traverses the standard generic submissions/document route.
    """
    validate_policy(
        policy
    )

    groups = validate_identity_contract(
        contract
    )

    if (
        policy[
            "authority"
        ].get(
            "authoritative_source_capture"
        )
        is not True
    ):
        raise AuthoritativeTaxonomySECExecutorError(
            "Current policy does not authorize live source capture."
        )

    _validate_authorization(
        authorization,
        manifest_sha256=
            manifest_sha256,
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
        raise AuthoritativeTaxonomySECExecutorError(
            "Identifying SEC User-Agent with email is required."
        )

    timeout = int(
        authorization[
            "request_timeout_seconds"
        ]
    )

    rate = float(
        authorization[
            "maximum_requests_per_second"
        ]
    )

    maximum_requests = int(
        authorization[
            "maximum_unique_sec_requests"
        ]
    )

    maximum_candidates = int(
        authorization[
            "maximum_candidate_filings_per_security"
        ]
    )

    root = Path(
        raw_root
    )

    request_cache: dict[
        str,
        tuple[int, str, bytes]
    ] = {}

    request_count = 0

    def governed_fetch(
        url: str,
    ) -> tuple[
        int,
        str,
        bytes,
    ]:
        nonlocal request_count

        if url in request_cache:
            return request_cache[
                url
            ]

        if request_count >= maximum_requests:
            raise AuthoritativeTaxonomySECExecutorError(
                "Absolute SEC request ceiling exhausted."
            )

        if request_count > 0:
            sleeper(
                1.0 / rate
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

        request_count += 1

        if int(
            status
        ) != 200:
            raise AuthoritativeTaxonomySECExecutorError(
                f"SEC returned HTTP {status}: {url}"
            )

        if not payload:
            raise AuthoritativeTaxonomySECExecutorError(
                f"SEC returned empty payload: {url}"
            )

        result = (
            int(status),
            str(final_url),
            payload,
        )

        request_cache[
            url
        ] = result

        return result

    output_records = []

    for group in sorted(
        groups,
        key=lambda value: int(
            value[
                "execution_order"
            ]
        ),
    ):
        cik = _normalize_cik(
            group["sec_cik"]
        )

        # --------------------------------------------------------
        # REMEDIATION LANE
        #
        # Do NOT send this group through standard SEC submissions
        # or recent-document routing.
        # --------------------------------------------------------

        if (
            group["lane"]
            == REMEDIATION_LANE
        ):
            for member in group[
                "security_identities"
            ]:
                record = _base_record(
                    member=member,
                    group=group,
                    cik=cik,
                )

                record.update(
                    {
                        "review_state":
                            "GOVERNED_REMEDIATION_ROUTE_PRESERVED",

                        "acquisition_state":
                            "UNRESOLVED",

                        "acquisition_reasons": [
                            "GOVERNED_EXISTING_REMEDIATION_ROUTE_REQUIRED"
                        ],

                        "submissions_url":
                            None,

                        "submission_http_status":
                            None,

                        "submission_final_url":
                            None,

                        "submission_content_sha256":
                            None,

                        "candidate_filing_count":
                            0,

                        "evaluated_candidate_count":
                            0,

                        "delegated_executor":
                            "EXISTING_SERIES_CLASS_REMEDIATION_ARCHITECTURE",
                    }
                )

                output_records.append(
                    record
                )

            continue

        # --------------------------------------------------------
        # STANDARD REGISTRANT LANE
        # --------------------------------------------------------

        submission_url = submissions_url(
            cik
        )

        (
            submission_status,
            submission_final_url,
            submission_payload,
        ) = governed_fetch(
            submission_url
        )

        try:
            submissions = json.loads(
                submission_payload.decode(
                    "utf-8-sig"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise AuthoritativeTaxonomySECExecutorError(
                f"Invalid SEC submissions JSON for CIK {cik}."
            ) from exc

        submission_sha = sha256_bytes(
            submission_payload
        )

        # Content-addressed storage makes repeated production runs
        # resume-safe when the SEC submissions document changes.
        submission_path = (
            root
            / "sec_taxonomy"
            / "submissions"
            / f"CIK{cik}"
            / f"{submission_sha}.json"
        )

        write_immutable(
            submission_path,
            submission_payload,
        )

        for member in group[
            "security_identities"
        ]:
            identity = {
                "security_id":
                    member[
                        "security_id"
                    ],

                "symbol":
                    member[
                        "symbol"
                    ],

                "sec_cik":
                    cik,

                "sec_series_id":
                    member[
                        "sec_series_id"
                    ],

                "sec_class_contract_id":
                    member[
                        "sec_class_contract_id"
                    ],
            }

            candidate_filings = (
                iter_candidate_filings(
                    submissions,
                    ALLOWED_FORMS,
                    maximum_candidates,
                )
            )

            evaluated_candidates = []

            for candidate in candidate_filings:
                accession = candidate[
                    "accession_number"
                ]

                primary_document = candidate[
                    "primary_document"
                ]

                if (
                    not accession
                    or not primary_document
                ):
                    continue

                url = filing_document_url(
                    cik,
                    accession,
                    primary_document,
                )

                (
                    document_status,
                    document_final_url,
                    document_payload,
                ) = governed_fetch(
                    url
                )

                accession_flat = accession.replace(
                    "-",
                    "",
                )

                document_path = (
                    root
                    / "sec_taxonomy"
                    / "filings"
                    / f"CIK{cik}"
                    / accession_flat
                    / primary_document
                )

                write_immutable(
                    document_path,
                    document_payload,
                )

                evaluation = evaluate_candidate(
                    identity,
                    document_payload,
                )

                evaluated_candidates.append(
                    {
                        **candidate,
                        **evaluation,

                        "source_url":
                            url,

                        "final_url":
                            document_final_url,

                        "http_status":
                            document_status,

                        "content_sha256":
                            sha256_bytes(
                                document_payload
                            ),

                        "byte_count":
                            len(
                                document_payload
                            ),

                        "raw_path":
                            str(
                                document_path
                            ),
                    }
                )

            resolution = choose_resolution(
                identity,
                evaluated_candidates,
            )

            review_state = resolution[
                "review_state"
            ]

            record = _base_record(
                member=member,
                group=group,
                cik=cik,
            )

            record.update(
                {
                    "submissions_url":
                        submission_url,

                    "submission_http_status":
                        submission_status,

                    "submission_final_url":
                        submission_final_url,

                    "submission_content_sha256":
                        submission_sha,

                    "submission_raw_path":
                        str(
                            submission_path
                        ),

                    "candidate_filing_count":
                        len(
                            candidate_filings
                        ),

                    "evaluated_candidate_count":
                        len(
                            evaluated_candidates
                        ),

                    "review_state":
                        review_state,
                }
            )

            if (
                review_state
                == "SERIES_CLASS_DOCUMENT_RESOLVED"
            ):
                record.update(
                    {
                        "acquisition_state":
                            "AUTHORITY_CAPTURED",

                        "source_tier":
                            "SEC_FILING",

                        "source_id":
                            "SEC_EDGAR",

                        "source_record_id":
                            resolution[
                                "accession_number"
                            ],

                        "source_url":
                            resolution[
                                "source_url"
                            ],

                        "content_sha256":
                            resolution[
                                "content_sha256"
                            ],

                        "acquisition_reasons": [
                            "PRODUCT_SPECIFIC_SEC_FILING_CAPTURED"
                        ],
                    }
                )

            elif (
                review_state
                == "SERIES_CLASS_DOCUMENT_CONFLICTED"
            ):
                record.update(
                    {
                        "acquisition_state":
                            "CONFLICTED",

                        "acquisition_reasons": [
                            "MULTIPLE_PRODUCT_SPECIFIC_SEC_FILINGS_MATCHED"
                        ],
                    }
                )

            else:
                record.update(
                    {
                        "acquisition_state":
                            "UNRESOLVED",

                        "acquisition_reasons": [
                            "PRODUCT_SPECIFIC_SEC_FILING_NOT_RESOLVED"
                        ],
                    }
                )

            output_records.append(
                record
            )

    if len(
        output_records
    ) != EXPECTED_POPULATION:
        raise AuthoritativeTaxonomySECExecutorError(
            "Executor output does not account for all 1,077 ETFs."
        )

    acquisition_counts = Counter(
        record[
            "acquisition_state"
        ]
        for record
        in output_records
    )

    reason_counts = Counter(
        reason
        for record
        in output_records
        for reason
        in record[
            "acquisition_reasons"
        ]
    )

    return {
        "artifact_id":
            "ETF_1077_AUTHORITATIVE_SEC_CAPTURE_LEDGER",

        "governed_population":
            EXPECTED_POPULATION,

        "registrant_group_count":
            EXPECTED_GROUP_COUNT,

        "standard_registrant_count":
            EXPECTED_STANDARD_GROUPS,

        "standard_etf_count":
            EXPECTED_STANDARD_ETFS,

        "remediation_registrant_count":
            EXPECTED_REMEDIATION_GROUPS,

        "remediation_etf_count":
            EXPECTED_REMEDIATION_ETFS,

        "record_count":
            len(
                output_records
            ),

        "unique_sec_requests_performed":
            request_count,

        "acquisition_state_counts":
            dict(
                sorted(
                    acquisition_counts.items()
                )
            ),

        "acquisition_reason_counts":
            dict(
                sorted(
                    reason_counts.items()
                )
            ),

        "taxonomy_classification_performed":
            0,

        "taxonomy_normalization_performed":
            0,

        "records":
            output_records,
    }
