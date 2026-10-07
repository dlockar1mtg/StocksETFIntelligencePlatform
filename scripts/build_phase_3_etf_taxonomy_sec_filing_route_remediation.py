from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OPERATING_DATE = "2026-08-06"

PRIORITY_COUNT = 215
EXISTING_ROUTE_COUNT = 0
DISCOVERY_REQUIRED_COUNT = 215
DISPROVEN_ROUTE_COUNT = 4
REFERENCE_ONLY_COUNT = 1

INVALID_SHARED_PAYLOAD_SHA256 = (
    "20f61b13e683a7b17cad51aeebed191fa"
    "4a95064a57c89ce6b884d0c01f1c0b7"
)

POLICY_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "market"
    / "etf_taxonomy_sec_filing_route_remediation_policy.json"
)

TAXONOMY_SCOPE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_taxonomy_scope"
    / OPERATING_DATE
    / "phase_3_etf_model_taxonomy_scope.json"
)


ACTIVE_STRUCTURAL_UNIVERSE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "active_universe"
    / "2026-08-03"
    / "active_structural_universe.json"
)

EXECUTION_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "priority_batch_controlled_source_capture_execution"
    / "2026-08-05"
    / "priority_batch_controlled_source_capture_execution_ledger.json"
)

REVIEW_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "priority_batch_capture_ledger_review"
    / "2026-08-05"
    / "priority_batch_capture_ledger_review.json"
)

PRODUCT_REMEDIATION_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "sec_product_specific_filing_document_route_remediation"
    / "2026-08-05"
    / "sec_product_specific_filing_document_route_remediation_ledger.json"
)

SERIES_RESOLUTION_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "sec_series_class_specific_filing_resolution"
    / "2026-08-05"
    / "sec_series_class_specific_filing_resolution_ledger.json"
)

OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "etf_taxonomy_sec_filing_route_remediation"
    / OPERATING_DATE
)

PLAN_PATH = (
    OUTPUT_DIRECTORY
    / "etf_taxonomy_sec_filing_route_remediation_plan.json"
)

LEDGER_PATH = (
    OUTPUT_DIRECTORY
    / "etf_taxonomy_sec_filing_route_remediation_decision_ledger.json"
)

SUMMARY_PATH = (
    OUTPUT_DIRECTORY
    / "etf_taxonomy_sec_filing_route_remediation_summary.json"
)


class RemediationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RemediationError(f"Missing required source: {path}")

    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise RemediationError(f"Expected JSON object: {path}")

    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def sha256_document(document: Any) -> str:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def index_records(
    document: dict[str, Any],
    source_name: str,
) -> dict[str, dict[str, Any]]:
    records = document.get("records")

    if not isinstance(records, list):
        raise RemediationError(
            f"{source_name} does not contain a records list."
        )

    result: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            raise RemediationError(
                f"{source_name} contains a non-object record."
            )

        security_id = record.get("security_id")

        if not isinstance(security_id, str) or not security_id:
            raise RemediationError(
                f"{source_name} contains a missing security_id."
            )

        if security_id in result:
            raise RemediationError(
                f"{source_name} contains duplicate security_id "
                f"{security_id!r}."
            )

        result[security_id] = record

    return result


def first_value(
    record: dict[str, Any] | None,
    names: tuple[str, ...],
) -> Any:
    if record is None:
        return None

    for name in names:
        value = record.get(name)

        if value is not None and value != "":
            return value

    return None


def is_archives_filing_document_url(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False

    parsed = urlparse(value)

    return (
        parsed.scheme == "https"
        and parsed.netloc.lower() == "www.sec.gov"
        and parsed.path.lower().startswith("/archives/edgar/data/")
        and parsed.path.lower().endswith(
            (".htm", ".html", ".txt", ".xml")
        )
    )


def main() -> None:
    policy = load_json(POLICY_PATH)
    scope = load_json(TAXONOMY_SCOPE_PATH)
    active_structural_universe = load_json(
        ACTIVE_STRUCTURAL_UNIVERSE_PATH
    )
    execution = load_json(EXECUTION_PATH)
    review = load_json(REVIEW_PATH)
    product_remediation = load_json(PRODUCT_REMEDIATION_PATH)
    series_resolution = load_json(SERIES_RESOLUTION_PATH)

    scope_records = scope.get("records")

    if not isinstance(scope_records, list):
        raise RemediationError(
            "Taxonomy scope does not contain records."
        )

    priority_records = [
        record
        for record in scope_records
        if record.get("workstream_membership", {}).get(
            "priority_remediation_scope"
        )
        is True
    ]

    if len(priority_records) != PRIORITY_COUNT:
        raise RemediationError(
            f"Expected {PRIORITY_COUNT} priority records; "
            f"found {len(priority_records)}."
        )

    priority_index = index_records(
        {"records": priority_records},
        "Priority taxonomy scope",
    )

    structural_index = index_records(
        active_structural_universe,
        "Active structural universe",
    )

    execution_index = index_records(
        execution,
        "Capture execution ledger",
    )

    review_index = index_records(
        review,
        "Capture review ledger",
    )

    product_index = index_records(
        product_remediation,
        "Product remediation ledger",
    )

    series_index = index_records(
        series_resolution,
        "Series resolution ledger",
    )

    priority_ids = set(priority_index)
    remediation_common_ids = set(product_index) & set(series_index)

    priority_remediation_ids = remediation_common_ids & priority_ids
    reference_only_remediation_ids = (
        remediation_common_ids - priority_ids
    )

    disproven_symbols = set(
        policy["disproven_route_controls"][
            "disproven_existing_route_symbols"
        ]
    )

    disproven_priority_ids = {
        security_id
        for security_id in priority_remediation_ids
        if priority_index[security_id].get("symbol")
        in disproven_symbols
    }

    if len(disproven_priority_ids) != DISPROVEN_ROUTE_COUNT:
        raise RemediationError(
            "Disproven model-priority route count mismatch."
        )

    unexpected_priority_remediation_ids = (
        priority_remediation_ids
        - disproven_priority_ids
    )

    if unexpected_priority_remediation_ids:
        raise RemediationError(
            "Unexpected model-priority remediation routes exist: "
            + ", ".join(
                sorted(
                    unexpected_priority_remediation_ids
                )
            )
        )

    if len(reference_only_remediation_ids) != REFERENCE_ONLY_COUNT:
        raise RemediationError(
            "Reference-only remediation count mismatch."
        )

    source_hashes = {
        "policy_sha256": sha256_file(POLICY_PATH),
        "taxonomy_scope_sha256": sha256_file(
            TAXONOMY_SCOPE_PATH
        ),
        "active_structural_universe_sha256": sha256_file(
            ACTIVE_STRUCTURAL_UNIVERSE_PATH
        ),
        "capture_execution_sha256": sha256_file(
            EXECUTION_PATH
        ),
        "capture_review_sha256": sha256_file(
            REVIEW_PATH
        ),
        "product_remediation_sha256": sha256_file(
            PRODUCT_REMEDIATION_PATH
        ),
        "series_resolution_sha256": sha256_file(
            SERIES_RESOLUTION_PATH
        ),
    }

    plan_records: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []

    for security_id in sorted(priority_ids):
        scope_record = priority_index[security_id]
        structural_record = structural_index.get(security_id)
        execution_record = execution_index.get(security_id)
        review_record = review_index.get(security_id)
        product_record = product_index.get(security_id)
        series_record = series_index.get(security_id)

        if structural_record is None:
            raise RemediationError(
                f"Missing structural identity record: {security_id}"
            )

        if execution_record is None:
            raise RemediationError(
                f"Missing execution record: {security_id}"
            )

        if review_record is None:
            raise RemediationError(
                f"Missing review record: {security_id}"
            )

        symbol = scope_record.get("symbol")

        if not isinstance(symbol, str) or not symbol:
            raise RemediationError(
                f"Missing symbol for {security_id}."
            )

        payload_sha256 = first_value(
            execution_record,
            (
                "payload_sha256",
                "content_sha256",
                "sha256",
            ),
        )

        review_state = first_value(
            review_record,
            (
                "review_state",
                "status",
            ),
        )

        if payload_sha256 != INVALID_SHARED_PAYLOAD_SHA256:
            raise RemediationError(
                f"{security_id}: unexpected prior payload hash."
            )

        if review_state != "GENERIC_SHARED_PAYLOAD":
            raise RemediationError(
                f"{security_id}: unexpected review state "
                f"{review_state!r}."
            )

        product_url = first_value(
            product_record,
            (
                "product_specific_url",
                "resolved_url",
                "remediated_url",
                "document_url",
                "filing_url",
                "url",
            ),
        )

        sec_cik = first_value(
            structural_record,
            (
                "sec_cik",
                "cik",
            ),
        )

        series_id = first_value(
            structural_record,
            (
                "sec_series_id",
                "series_id",
            ),
        )

        class_id = first_value(
            structural_record,
            (
                "sec_class_contract_id",
                "class_contract_id",
                "class_id",
            ),
        )

        if (
            not isinstance(sec_cik, str)
            or not sec_cik
            or not isinstance(series_id, str)
            or not series_id
            or not isinstance(class_id, str)
            or not class_id
        ):
            raise RemediationError(
                f"{security_id}: structural SEC identity incomplete."
            )

        is_disproven_route = (
            security_id in disproven_priority_ids
        )

        if (
            is_disproven_route
            and not is_archives_filing_document_url(
                product_url
            )
        ):
            raise RemediationError(
                f"{security_id}: disproven route evidence "
                "is not preserved as an SEC Archives document."
            )

        if (
            not is_disproven_route
            and product_url is not None
        ):
            raise RemediationError(
                f"{security_id}: unexpected product-specific "
                "route outside the disproven route set."
            )

        queue = "FILING_ROUTE_DISCOVERY_REQUIRED"

        authority = {
            "network_capture_authorized": False,
            "taxonomy_normalization_authorized": False,
            "taxonomy_classification_authorized": False,
            "benchmark_assignment_authorized": False,
            "ranking_authorized": False,
            "forecasting_authorized": False,
            "recommendations_authorized": False,
            "allocation_authorized": False,
            "automatic_execution_authorized": False,
            "uip_database_write_authorized": False,
        }

        plan_records.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "remediation_queue": queue,
                "prior_capture_state": first_value(
                    execution_record,
                    ("capture_state", "status"),
                ),
                "prior_review_state": review_state,
                "prior_payload_sha256": payload_sha256,
                "prior_capture_usable": False,
                "candidate_product_specific_filing_url": None,
                "disproven_product_specific_filing_url": (
                    product_url
                    if is_disproven_route
                    else None
                ),
                "prior_route_disposition": (
                    "MISRESOLVED_FILING_ROUTE_REJECTED"
                    if is_disproven_route
                    else "NO_PRIOR_PRODUCT_SPECIFIC_ROUTE"
                ),
                "sec_cik": sec_cik,
                "sec_series_id": series_id,
                "sec_class_contract_id": class_id,
                "identity_source": (
                    "ACTIVE_STRUCTURAL_UNIVERSE"
                ),
                "required_next_action": (
                    "RESOLVE_PRODUCT_SPECIFIC_FILING_DOCUMENT"
                ),
                "authority": authority,
            }
        )

        ledger_records.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "inside_model_priority_scope": True,
                "remediation_queue": queue,
                "reference_only_blocked": False,
                "authority": authority,
            }
        )

    for security_id in sorted(reference_only_remediation_ids):
        product_record = product_index[security_id]
        series_record = series_index[security_id]

        ledger_records.append(
            {
                "security_id": security_id,
                "symbol": first_value(
                    product_record,
                    ("symbol",),
                ),
                "inside_model_priority_scope": False,
                "remediation_queue": "REFERENCE_ONLY_BLOCKED",
                "reference_only_blocked": True,
                "candidate_product_specific_filing_url": first_value(
                    product_record,
                    (
                        "product_specific_url",
                        "resolved_url",
                        "remediated_url",
                        "document_url",
                        "filing_url",
                        "url",
                    ),
                ),
                "sec_series_id": first_value(
                    series_record,
                    ("series_id", "sec_series_id"),
                ),
                "sec_class_contract_id": first_value(
                    series_record,
                    (
                        "class_id",
                        "class_contract_id",
                        "sec_class_id",
                    ),
                ),
                "authority": {
                    "network_capture_authorized": False,
                    "taxonomy_normalization_authorized": False,
                    "taxonomy_classification_authorized": False,
                    "benchmark_assignment_authorized": False,
                    "ranking_authorized": False,
                    "forecasting_authorized": False,
                    "recommendations_authorized": False,
                    "allocation_authorized": False,
                    "automatic_execution_authorized": False,
                    "uip_database_write_authorized": False,
                },
            }
        )

    existing_route_records = [
        record
        for record in plan_records
        if record["remediation_queue"]
        == "EXISTING_FILING_ROUTE_VALIDATION_REQUIRED"
    ]

    discovery_records = [
        record
        for record in plan_records
        if record["remediation_queue"]
        == "FILING_ROUTE_DISCOVERY_REQUIRED"
    ]

    if len(existing_route_records) != EXISTING_ROUTE_COUNT:
        raise RemediationError(
            "Existing filing-route queue count mismatch."
        )

    if existing_route_records:
        raise RemediationError(
            "No disproven filing route may remain "
            "in the existing-route validation queue."
        )

    if len(discovery_records) != DISCOVERY_REQUIRED_COUNT:
        raise RemediationError(
            "Filing-route discovery queue count mismatch."
        )

    plan = {
        "artifact_id": (
            "ETF_TAXONOMY_SEC_FILING_ROUTE_REMEDIATION_PLAN"
        ),
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "priority_population_count": PRIORITY_COUNT,
        "existing_filing_route_validation_count": (
            len(existing_route_records)
        ),
        "filing_route_discovery_required_count": (
            len(discovery_records)
        ),
        "disproven_existing_route_count": (
            len(disproven_priority_ids)
        ),
        "invalid_shared_payload_sha256": (
            INVALID_SHARED_PAYLOAD_SHA256
        ),
        "source_hashes": source_hashes,
        "records": plan_records,
    }

    ledger = {
        "artifact_id": (
            "ETF_TAXONOMY_SEC_FILING_ROUTE_REMEDIATION_"
            "DECISION_LEDGER"
        ),
        "operating_date": OPERATING_DATE,
        "model_priority_count": PRIORITY_COUNT,
        "reference_only_blocked_count": (
            len(reference_only_remediation_ids)
        ),
        "source_hashes": source_hashes,
        "records": ledger_records,
    }

    plan_sha256 = sha256_document(plan)
    ledger_sha256 = sha256_document(ledger)

    summary = {
        "artifact_id": (
            "ETF_TAXONOMY_SEC_FILING_ROUTE_REMEDIATION_SUMMARY"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "operating_date": OPERATING_DATE,
        "planning_state": "PLAN_COMPLETE",
        "critical_failures": [],
        "priority_population_count": PRIORITY_COUNT,
        "existing_filing_route_validation_count": (
            len(existing_route_records)
        ),
        "filing_route_discovery_required_count": (
            len(discovery_records)
        ),
        "disproven_existing_route_count": (
            len(disproven_priority_ids)
        ),
        "reference_only_blocked_count": (
            len(reference_only_remediation_ids)
        ),
        "network_capture_authorized": False,
        "taxonomy_normalization_authorized": False,
        "plan_sha256": plan_sha256,
        "decision_ledger_sha256": ledger_sha256,
        "source_hashes": source_hashes,
    }

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    for path, document in (
        (PLAN_PATH, plan),
        (LEDGER_PATH, ledger),
        (SUMMARY_PATH, summary),
    ):
        with path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            json.dump(
                document,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            handle.write("\n")

    print("=" * 72)
    print("ETF Taxonomy SEC Filing-Route Remediation Plan")
    print("=" * 72)
    print(f"Priority population:              {PRIORITY_COUNT}")
    print(
        "Existing filing routes:           "
        f"{len(existing_route_records)}"
    )
    print(
        "Disproven routes rejected:        "
        f"{len(disproven_priority_ids)}"
    )
    print(
        "Filing-route discovery required:  "
        f"{len(discovery_records)}"
    )
    print(
        "Reference-only blocked:            "
        f"{len(reference_only_remediation_ids)}"
    )
    print("Network capture authorized:        False")
    print("Taxonomy normalization authorized: False")
    print(f"Plan SHA-256:                      {plan_sha256}")
    print(f"Ledger SHA-256:                    {ledger_sha256}")
    print("")
    print(f"Plan:    {PLAN_PATH}")
    print(f"Ledger:  {LEDGER_PATH}")
    print(f"Summary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
