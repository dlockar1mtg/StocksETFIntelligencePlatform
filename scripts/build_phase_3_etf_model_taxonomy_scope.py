from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OPERATING_DATE = "2026-08-06"
REFERENCE_COUNT = 3462
MODEL_COUNT = 1077
PRIORITY_MODEL_COUNT = 215
PRIORITY_OUTSIDE_MODEL_COUNT = 132
ROUTE_PILOT_MODEL_COUNT = 4
ROUTE_PILOT_OUTSIDE_MODEL_COUNT = 1
NORMALIZED_PILOT_MODEL_COUNT = 3

REQUIRED_SEEDS = {"VOO", "SCHD", "QQQM"}

MODEL_UNIVERSE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_universe"
    / OPERATING_DATE
    / "phase_3_etf_model_universe.json"
)

MODEL_DECISION_LEDGER_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_universe"
    / OPERATING_DATE
    / "phase_3_etf_model_universe_decision_ledger.json"
)

AUTHORITATIVE_TAXONOMY_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "authoritative_etf_taxonomy"
    / "2026-08-04"
    / "authoritative_etf_taxonomy_snapshot.json"
)

PRODUCTION_TAXONOMY_EVIDENCE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "production_etf_taxonomy_evidence"
    / "2026-08-04"
    / "production_etf_taxonomy_evidence.json"
)

PRIORITY_BATCH_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "priority_batch_capture_ledger_review"
    / "2026-08-05"
    / "priority_batch_capture_ledger_review.json"
)

ROUTE_PILOT_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "priority_batch_route_discovery_pilot"
    / "2026-08-04"
    / "priority_batch_route_discovery_pilot_manifest.json"
)

ROUTE_PILOT_EXECUTION_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "priority_batch_route_discovery_pilot_execution"
    / "2026-08-04"
    / "priority_batch_route_discovery_pilot_execution_ledger.json"
)

NORMALIZED_PILOT_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "pilot_taxonomy_normalization"
    / "2026-08-04"
    / "pilot_taxonomy_snapshot.json"
)

POLICY_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "market"
    / "etf_model_taxonomy_scope_policy.json"
)

OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_taxonomy_scope"
    / OPERATING_DATE
)

SCOPE_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_taxonomy_scope.json"
)

DECISION_LEDGER_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_taxonomy_scope_decision_ledger.json"
)

CERTIFICATION_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_taxonomy_scope_certification.json"
)


class ScopeCertificationError(RuntimeError):
    """Raised when taxonomy-scope certification fails."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ScopeCertificationError(
            f"Missing required source: {path}"
        )

    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise ScopeCertificationError(
            f"Expected JSON object in {path}"
        )

    return value


def index_records(
    document: dict[str, Any],
    source_name: str,
    expected_count: int | None = None,
) -> dict[str, dict[str, Any]]:
    records = document.get("records")

    if not isinstance(records, list):
        raise ScopeCertificationError(
            f"{source_name} does not contain a records list."
        )

    if expected_count is not None and len(records) != expected_count:
        raise ScopeCertificationError(
            f"{source_name} expected {expected_count} records; "
            f"found {len(records)}."
        )

    result: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            raise ScopeCertificationError(
                f"{source_name} contains a non-object record."
            )

        security_id = record.get("security_id")

        if not isinstance(security_id, str) or not security_id:
            raise ScopeCertificationError(
                f"{source_name} contains a missing security_id."
            )

        if security_id in result:
            raise ScopeCertificationError(
                f"{source_name} contains duplicate security_id "
                f"{security_id!r}."
            )

        result[security_id] = record

    return result


def read_symbol(
    record: dict[str, Any],
    source_name: str,
    security_id: str,
) -> str:
    symbol = record.get("symbol")

    if not isinstance(symbol, str) or not symbol:
        raise ScopeCertificationError(
            f"{source_name} record {security_id} has no symbol."
        )

    return symbol


def main() -> None:
    policy = load_json(POLICY_PATH)

    model_document = load_json(MODEL_UNIVERSE_PATH)
    model_ledger_document = load_json(MODEL_DECISION_LEDGER_PATH)
    authoritative_document = load_json(
        AUTHORITATIVE_TAXONOMY_PATH
    )
    production_document = load_json(
        PRODUCTION_TAXONOMY_EVIDENCE_PATH
    )
    priority_document = load_json(PRIORITY_BATCH_PATH)
    route_pilot_document = load_json(ROUTE_PILOT_PATH)
    route_execution_document = load_json(
        ROUTE_PILOT_EXECUTION_PATH
    )
    normalized_document = load_json(NORMALIZED_PILOT_PATH)

    model_index = index_records(
        model_document,
        "ETF model universe",
        MODEL_COUNT,
    )

    model_ledger_index = index_records(
        model_ledger_document,
        "ETF model decision ledger",
        REFERENCE_COUNT,
    )

    authoritative_index = index_records(
        authoritative_document,
        "authoritative taxonomy",
        REFERENCE_COUNT,
    )

    production_index = index_records(
        production_document,
        "production taxonomy evidence",
        REFERENCE_COUNT,
    )

    priority_index = index_records(
        priority_document,
        "priority batch",
        347,
    )

    route_pilot_index = index_records(
        route_pilot_document,
        "route pilot",
        5,
    )

    route_execution_index = index_records(
        route_execution_document,
        "route pilot execution",
        5,
    )

    normalized_index = index_records(
        normalized_document,
        "normalized pilot",
        3,
    )

    model_ids = set(model_index)
    reference_ids = set(model_ledger_index)

    if len(model_ids) != MODEL_COUNT:
        raise ScopeCertificationError(
            "Model universe security population is invalid."
        )

    if len(reference_ids) != REFERENCE_COUNT:
        raise ScopeCertificationError(
            "Reference decision population is invalid."
        )

    if not model_ids <= reference_ids:
        raise ScopeCertificationError(
            "Model universe is not a subset of the reference ledger."
        )

    for source_name, source_index in (
        ("authoritative taxonomy", authoritative_index),
        ("production taxonomy evidence", production_index),
    ):
        if set(source_index) != reference_ids:
            raise ScopeCertificationError(
                f"{source_name} does not match the reference population."
            )

    priority_model_ids = set(priority_index) & model_ids
    priority_outside_model_ids = set(priority_index) - model_ids

    route_model_ids = set(route_pilot_index) & model_ids
    route_outside_model_ids = set(route_pilot_index) - model_ids

    route_execution_model_ids = (
        set(route_execution_index) & model_ids
    )

    normalized_model_ids = set(normalized_index) & model_ids

    if len(priority_model_ids) != PRIORITY_MODEL_COUNT:
        raise ScopeCertificationError(
            f"Expected {PRIORITY_MODEL_COUNT} model priority records; "
            f"found {len(priority_model_ids)}."
        )

    if (
        len(priority_outside_model_ids)
        != PRIORITY_OUTSIDE_MODEL_COUNT
    ):
        raise ScopeCertificationError(
            "Priority outside-model count mismatch."
        )

    if len(route_model_ids) != ROUTE_PILOT_MODEL_COUNT:
        raise ScopeCertificationError(
            "Route-pilot model count mismatch."
        )

    if (
        len(route_outside_model_ids)
        != ROUTE_PILOT_OUTSIDE_MODEL_COUNT
    ):
        raise ScopeCertificationError(
            "Route-pilot outside-model count mismatch."
        )

    if route_execution_model_ids != route_model_ids:
        raise ScopeCertificationError(
            "Route-pilot plan and execution populations disagree."
        )

    if len(normalized_model_ids) != NORMALIZED_PILOT_MODEL_COUNT:
        raise ScopeCertificationError(
            "Normalized-pilot model count mismatch."
        )

    source_hashes = {
        "policy_sha256": sha256_file(POLICY_PATH),
        "model_universe_sha256": sha256_file(
            MODEL_UNIVERSE_PATH
        ),
        "model_decision_ledger_sha256": sha256_file(
            MODEL_DECISION_LEDGER_PATH
        ),
        "authoritative_taxonomy_sha256": sha256_file(
            AUTHORITATIVE_TAXONOMY_PATH
        ),
        "production_taxonomy_evidence_sha256": sha256_file(
            PRODUCTION_TAXONOMY_EVIDENCE_PATH
        ),
        "priority_batch_sha256": sha256_file(
            PRIORITY_BATCH_PATH
        ),
        "route_pilot_sha256": sha256_file(
            ROUTE_PILOT_PATH
        ),
        "route_pilot_execution_sha256": sha256_file(
            ROUTE_PILOT_EXECUTION_PATH
        ),
        "normalized_pilot_sha256": sha256_file(
            NORMALIZED_PILOT_PATH
        ),
    }

    decisions: list[dict[str, Any]] = []

    for security_id in sorted(reference_ids):
        reference_record = model_ledger_index[security_id]
        inside_model = security_id in model_ids

        symbol = read_symbol(
            reference_record,
            "ETF model decision ledger",
            security_id,
        )

        if inside_model:
            model_symbol = read_symbol(
                model_index[security_id],
                "ETF model universe",
                security_id,
            )

            if model_symbol != symbol:
                raise ScopeCertificationError(
                    f"{security_id}: model/reference symbol mismatch."
                )

        decisions.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "inside_etf_model_universe": inside_model,
                "taxonomy_scope_state": (
                    "ETF_MODEL_TAXONOMY_INCLUDED"
                    if inside_model
                    else "ETF_REFERENCE_ONLY_TAXONOMY_BLOCKED"
                ),
                "priority_batch_member": (
                    security_id in priority_index
                ),
                "priority_batch_model_member": (
                    security_id in priority_model_ids
                ),
                "route_pilot_member": (
                    security_id in route_pilot_index
                ),
                "route_pilot_model_member": (
                    security_id in route_model_ids
                ),
                "normalized_pilot_member": (
                    security_id in normalized_index
                ),
                "existing_source_presence": {
                    "authoritative_taxonomy": (
                        security_id in authoritative_index
                    ),
                    "production_taxonomy_evidence": (
                        security_id in production_index
                    ),
                },
                "authority": {
                    "taxonomy_development_authorized": (
                        inside_model
                    ),
                    "taxonomy_source_acquisition_authorized": (
                        inside_model
                    ),
                    "taxonomy_normalization_authorized": (
                        inside_model
                    ),
                    "benchmark_assignment_authorized": False,
                    "risk_model_authorized": False,
                    "ranking_authorized": False,
                    "forecasting_authorized": False,
                    "recommendations_authorized": False,
                    "allocation_authorized": False,
                    "automatic_execution_authorized": False,
                    "uip_database_write_authorized": False,
                },
            }
        )

    included_decisions = [
        decision
        for decision in decisions
        if decision["inside_etf_model_universe"]
    ]

    blocked_decisions = [
        decision
        for decision in decisions
        if not decision["inside_etf_model_universe"]
    ]

    if len(included_decisions) != MODEL_COUNT:
        raise ScopeCertificationError(
            "Included taxonomy scope count mismatch."
        )

    if len(blocked_decisions) != REFERENCE_COUNT - MODEL_COUNT:
        raise ScopeCertificationError(
            "Blocked taxonomy scope count mismatch."
        )

    included_symbols = {
        decision["symbol"]
        for decision in included_decisions
    }

    missing_seeds = sorted(REQUIRED_SEEDS - included_symbols)

    if missing_seeds:
        raise ScopeCertificationError(
            f"Required seeds missing from taxonomy scope: "
            f"{missing_seeds}"
        )

    duplicate_symbols = [
        symbol
        for symbol, count in Counter(
            decision["symbol"]
            for decision in included_decisions
        ).items()
        if count > 1
    ]

    if duplicate_symbols:
        raise ScopeCertificationError(
            f"Duplicate taxonomy-scope symbols: "
            f"{sorted(duplicate_symbols)}"
        )

    scope_records: list[dict[str, Any]] = []

    for decision in included_decisions:
        security_id = decision["security_id"]

        scope_records.append(
            {
                "security_id": security_id,
                "symbol": decision["symbol"],
                "taxonomy_scope_state": (
                    decision["taxonomy_scope_state"]
                ),
                "workstream_membership": {
                    "full_taxonomy_development_scope": True,
                    "priority_remediation_scope": (
                        security_id in priority_model_ids
                    ),
                    "route_pilot_scope": (
                        security_id in route_model_ids
                    ),
                    "normalized_pilot_scope": (
                        security_id in normalized_model_ids
                    ),
                },
                "existing_source_presence": {
                    "authoritative_taxonomy": True,
                    "production_taxonomy_evidence": True,
                },
                "source_record_lineage": {
                    "authoritative_taxonomy_security_id": (
                        security_id
                    ),
                    "production_taxonomy_evidence_security_id": (
                        security_id
                    ),
                },
                "authority": decision["authority"],
            }
        )

    scope_document = {
        "artifact_id": "PHASE_3_ETF_MODEL_TAXONOMY_SCOPE",
        "scope_version": "2026-08-06-v1",
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "taxonomy_scope_count": len(scope_records),
        "reference_population_count": REFERENCE_COUNT,
        "taxonomy_blocked_reference_count": len(
            blocked_decisions
        ),
        "priority_remediation_scope_count": len(
            priority_model_ids
        ),
        "route_pilot_scope_count": len(route_model_ids),
        "normalized_pilot_scope_count": len(
            normalized_model_ids
        ),
        "required_seeds": sorted(REQUIRED_SEEDS),
        "source_hashes": source_hashes,
        "records": scope_records,
    }

    decision_ledger = {
        "artifact_id": (
            "PHASE_3_ETF_MODEL_TAXONOMY_SCOPE_DECISION_LEDGER"
        ),
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "reference_population_count": len(decisions),
        "taxonomy_scope_count": len(included_decisions),
        "taxonomy_blocked_reference_count": len(
            blocked_decisions
        ),
        "priority_batch_original_count": len(priority_index),
        "priority_batch_model_count": len(priority_model_ids),
        "priority_batch_reference_only_count": len(
            priority_outside_model_ids
        ),
        "route_pilot_original_count": len(route_pilot_index),
        "route_pilot_model_count": len(route_model_ids),
        "route_pilot_reference_only_count": len(
            route_outside_model_ids
        ),
        "normalized_pilot_model_count": len(
            normalized_model_ids
        ),
        "source_hashes": source_hashes,
        "records": decisions,
    }

    scope_sha256 = sha256_bytes(
        canonical_json_bytes(scope_document)
    )

    ledger_sha256 = sha256_bytes(
        canonical_json_bytes(decision_ledger)
    )

    certification = {
        "certification_id": (
            "PHASE_3_ETF_MODEL_TAXONOMY_SCOPE_CERTIFICATION"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "certification_state": "CERTIFIED",
        "critical_failures": [],
        "reference_population_count": REFERENCE_COUNT,
        "taxonomy_scope_count": MODEL_COUNT,
        "taxonomy_blocked_reference_count": (
            REFERENCE_COUNT - MODEL_COUNT
        ),
        "priority_batch_original_count": 347,
        "priority_batch_model_count": PRIORITY_MODEL_COUNT,
        "priority_batch_reference_only_count": (
            PRIORITY_OUTSIDE_MODEL_COUNT
        ),
        "route_pilot_original_count": 5,
        "route_pilot_model_count": ROUTE_PILOT_MODEL_COUNT,
        "route_pilot_reference_only_count": (
            ROUTE_PILOT_OUTSIDE_MODEL_COUNT
        ),
        "normalized_pilot_model_count": (
            NORMALIZED_PILOT_MODEL_COUNT
        ),
        "required_seeds": sorted(REQUIRED_SEEDS),
        "required_seeds_present": True,
        "taxonomy_scope_sha256": scope_sha256,
        "decision_ledger_sha256": ledger_sha256,
        "source_hashes": source_hashes,
        "authority": {
            "taxonomy_development_authorized": True,
            "taxonomy_source_acquisition_authorized": True,
            "taxonomy_normalization_authorized": True,
            "benchmark_assignment_authorized": False,
            "risk_model_authorized": False,
            "ranking_authorized": False,
            "forecasting_authorized": False,
            "recommendations_authorized": False,
            "allocation_authorized": False,
            "automatic_execution_authorized": False,
            "uip_database_write_authorized": False,
        },
    }

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    for path, document in (
        (SCOPE_PATH, scope_document),
        (DECISION_LEDGER_PATH, decision_ledger),
        (CERTIFICATION_PATH, certification),
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
    print("Phase 3 ETF Model Taxonomy-Scope Certification")
    print("=" * 72)
    print(f"Reference population:        {REFERENCE_COUNT}")
    print(f"Taxonomy model scope:        {MODEL_COUNT}")
    print(
        "Taxonomy blocked reference: "
        f"{REFERENCE_COUNT - MODEL_COUNT}"
    )
    print(f"Priority scope:              {len(priority_model_ids)}")
    print(f"Route-pilot scope:           {len(route_model_ids)}")
    print(
        "Normalized-pilot scope:      "
        f"{len(normalized_model_ids)}"
    )
    print("Certification state:         CERTIFIED")
    print(f"Scope SHA-256:               {scope_sha256}")
    print(f"Ledger SHA-256:              {ledger_sha256}")
    print("")
    print(f"Taxonomy scope:              {SCOPE_PATH}")
    print(f"Decision ledger:             {DECISION_LEDGER_PATH}")
    print(f"Certification:               {CERTIFICATION_PATH}")


if __name__ == "__main__":
    main()
