from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_universe"
    / "2026-08-06"
)

MODEL_PATH = OUTPUT_DIRECTORY / "phase_3_etf_model_universe.json"

LEDGER_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_universe_decision_ledger.json"
)

CERTIFICATION_PATH = (
    OUTPUT_DIRECTORY
    / "phase_3_etf_model_universe_certification.json"
)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def test_model_universe_has_required_population() -> None:
    document = load_json(MODEL_PATH)

    assert document["model_population_count"] == 1077
    assert len(document["records"]) == 1077
    assert document["reference_population_count"] == 3462
    assert document["excluded_reference_population_count"] == 2385


def test_decision_ledger_preserves_reference_population() -> None:
    document = load_json(LEDGER_PATH)

    assert document["reference_population_count"] == 3462
    assert len(document["records"]) == 3462
    assert document["included_model_population_count"] == 1077
    assert document["excluded_reference_population_count"] == 2385


def test_model_security_ids_and_symbols_are_unique() -> None:
    records = load_json(MODEL_PATH)["records"]

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


def test_required_seed_symbols_are_present() -> None:
    records = load_json(MODEL_PATH)["records"]

    symbols = {
        record["symbol"]
        for record in records
    }

    assert {"VOO", "SCHD", "QQQM"} <= symbols


def test_every_model_record_satisfies_inclusion_rules() -> None:
    records = load_json(MODEL_PATH)["records"]

    for record in records:
        conditions = record["inclusion_conditions"]
        evidence = record["evidence"]

        assert all(conditions.values())
        assert evidence["five_year_eligible"] is True
        assert (
            evidence["median_daily_dollar_volume_usd"]
            >= 1_000_000
        )
        assert (
            evidence["market_screen_state"]
            == "MARKET_DATA_ELIGIBLE"
        )
        assert (
            evidence["return_calculation_state"]
            == "CALCULATED"
        )
        assert evidence["issuer_identity_state"] in {
            "ISSUER_CONFIRMED",
            "PILOT_COMPLETE",
        }


def test_reference_only_records_have_no_model_authority() -> None:
    records = load_json(LEDGER_PATH)["records"]

    excluded = [
        record
        for record in records
        if not record["model_included"]
    ]

    assert len(excluded) == 2385

    for record in excluded:
        authority = record["downstream_authority"]

        assert authority["taxonomy_development_authorized"] is False
        assert authority["benchmark_assignment_authorized"] is False
        assert authority["risk_model_authorized"] is False
        assert authority["ranking_authorized"] is False
        assert authority["forecasting_authorized"] is False
        assert authority["recommendations_authorized"] is False
        assert authority["allocation_authorized"] is False
        assert authority["automatic_execution_authorized"] is False
        assert authority["uip_database_write_authorized"] is False


def test_certification_is_fail_closed() -> None:
    document = load_json(CERTIFICATION_PATH)

    assert document["certification_state"] == "CERTIFIED"
    assert document["critical_failures"] == []
    assert document["model_population_count"] == 1077
    assert document["required_model_population_count"] == 1077
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
