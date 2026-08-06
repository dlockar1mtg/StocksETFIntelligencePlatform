from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_taxonomy_scope"
    / "2026-08-06"
)

SCOPE_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_taxonomy_scope.json"
)

LEDGER_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_taxonomy_scope_decision_ledger.json"
)

CERTIFICATION_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_taxonomy_scope_certification.json"
)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def test_taxonomy_scope_population() -> None:
    document = load_json(SCOPE_PATH)

    assert document["taxonomy_scope_count"] == 1077
    assert len(document["records"]) == 1077
    assert document["reference_population_count"] == 3462
    assert document["taxonomy_blocked_reference_count"] == 2385


def test_taxonomy_decision_ledger_population() -> None:
    document = load_json(LEDGER_PATH)

    assert document["reference_population_count"] == 3462
    assert len(document["records"]) == 3462
    assert document["taxonomy_scope_count"] == 1077
    assert document["taxonomy_blocked_reference_count"] == 2385


def test_reset_intersection_counts() -> None:
    document = load_json(LEDGER_PATH)

    assert document["priority_batch_original_count"] == 347
    assert document["priority_batch_model_count"] == 215
    assert document["priority_batch_reference_only_count"] == 132

    assert document["route_pilot_original_count"] == 5
    assert document["route_pilot_model_count"] == 4
    assert document["route_pilot_reference_only_count"] == 1

    assert document["normalized_pilot_model_count"] == 3


def test_scope_security_ids_and_symbols_are_unique() -> None:
    records = load_json(SCOPE_PATH)["records"]

    security_ids = [
        record["security_id"]
        for record in records
    ]

    symbols = [
        record["symbol"]
        for record in records
    ]

    assert len(security_ids) == len(set(security_ids))
    assert len(symbols) == len(set(symbols))


def test_required_seeds_are_present() -> None:
    records = load_json(SCOPE_PATH)["records"]

    symbols = {
        record["symbol"]
        for record in records
    }

    assert {"VOO", "SCHD", "QQQM"} <= symbols


def test_all_scope_records_have_taxonomy_authority() -> None:
    records = load_json(SCOPE_PATH)["records"]

    for record in records:
        authority = record["authority"]

        assert record["taxonomy_scope_state"] == (
            "ETF_MODEL_TAXONOMY_INCLUDED"
        )

        assert authority["taxonomy_development_authorized"] is True
        assert (
            authority["taxonomy_source_acquisition_authorized"]
            is True
        )
        assert authority["taxonomy_normalization_authorized"] is True

        assert authority["benchmark_assignment_authorized"] is False
        assert authority["risk_model_authorized"] is False
        assert authority["ranking_authorized"] is False
        assert authority["forecasting_authorized"] is False
        assert authority["recommendations_authorized"] is False
        assert authority["allocation_authorized"] is False
        assert authority["automatic_execution_authorized"] is False
        assert authority["uip_database_write_authorized"] is False


def test_reference_only_records_are_taxonomy_blocked() -> None:
    records = load_json(LEDGER_PATH)["records"]

    blocked = [
        record
        for record in records
        if not record["inside_etf_model_universe"]
    ]

    assert len(blocked) == 2385

    for record in blocked:
        authority = record["authority"]

        assert record["taxonomy_scope_state"] == (
            "ETF_REFERENCE_ONLY_TAXONOMY_BLOCKED"
        )

        assert authority["taxonomy_development_authorized"] is False
        assert (
            authority["taxonomy_source_acquisition_authorized"]
            is False
        )
        assert authority["taxonomy_normalization_authorized"] is False


def test_certification_is_fail_closed() -> None:
    document = load_json(CERTIFICATION_PATH)

    assert document["certification_state"] == "CERTIFIED"
    assert document["critical_failures"] == []
    assert document["taxonomy_scope_count"] == 1077
    assert document["required_seeds_present"] is True

    authority = document["authority"]

    assert authority["taxonomy_development_authorized"] is True
    assert authority["benchmark_assignment_authorized"] is False
    assert authority["risk_model_authorized"] is False
    assert authority["ranking_authorized"] is False
    assert authority["forecasting_authorized"] is False
    assert authority["recommendations_authorized"] is False
    assert authority["allocation_authorized"] is False
    assert authority["automatic_execution_authorized"] is False
    assert authority["uip_database_write_authorized"] is False
