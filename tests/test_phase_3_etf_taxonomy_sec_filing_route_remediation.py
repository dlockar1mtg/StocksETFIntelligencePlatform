from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "etf_taxonomy_sec_filing_route_remediation"
    / "2026-08-06"
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


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def test_priority_plan_population() -> None:
    plan = load_json(PLAN_PATH)

    assert plan["priority_population_count"] == 215
    assert len(plan["records"]) == 215


def test_remediation_queue_counts() -> None:
    plan = load_json(PLAN_PATH)

    existing = [
        record
        for record in plan["records"]
        if record["remediation_queue"]
        == "EXISTING_FILING_ROUTE_VALIDATION_REQUIRED"
    ]

    discovery = [
        record
        for record in plan["records"]
        if record["remediation_queue"]
        == "FILING_ROUTE_DISCOVERY_REQUIRED"
    ]

    assert len(existing) == 4
    assert len(discovery) == 211


def test_reference_only_record_is_blocked() -> None:
    ledger = load_json(LEDGER_PATH)

    blocked = [
        record
        for record in ledger["records"]
        if record["reference_only_blocked"] is True
    ]

    assert len(blocked) == 1
    assert blocked[0]["symbol"] == "XVV"
    assert (
        blocked[0]["remediation_queue"]
        == "REFERENCE_ONLY_BLOCKED"
    )


def test_prior_shared_payload_is_rejected() -> None:
    plan = load_json(PLAN_PATH)

    assert plan["invalid_shared_payload_sha256"] == (
        "20f61b13e683a7b17cad51aeebed191fa"
        "4a95064a57c89ce6b884d0c01f1c0b7"
    )

    for record in plan["records"]:
        assert record["prior_capture_usable"] is False
        assert record["prior_review_state"] == (
            "GENERIC_SHARED_PAYLOAD"
        )


def test_existing_routes_have_sec_archive_documents() -> None:
    plan = load_json(PLAN_PATH)

    existing = [
        record
        for record in plan["records"]
        if record["remediation_queue"]
        == "EXISTING_FILING_ROUTE_VALIDATION_REQUIRED"
    ]

    for record in existing:
        url = record["candidate_product_specific_filing_url"]

        assert url.startswith(
            "https://www.sec.gov/Archives/edgar/data/"
        )

        assert url.lower().endswith(
            (".htm", ".html", ".txt", ".xml")
        )

        assert record["sec_series_id"]


def test_no_network_or_downstream_authority() -> None:
    plan = load_json(PLAN_PATH)

    for record in plan["records"]:
        authority = record["authority"]

        assert authority["network_capture_authorized"] is False
        assert (
            authority["taxonomy_normalization_authorized"]
            is False
        )
        assert (
            authority["taxonomy_classification_authorized"]
            is False
        )
        assert authority["ranking_authorized"] is False
        assert authority["forecasting_authorized"] is False
        assert authority["recommendations_authorized"] is False
        assert authority["allocation_authorized"] is False
        assert authority["automatic_execution_authorized"] is False
        assert authority["uip_database_write_authorized"] is False


def test_summary_is_plan_complete() -> None:
    summary = load_json(SUMMARY_PATH)

    assert summary["planning_state"] == "PLAN_COMPLETE"
    assert summary["critical_failures"] == []
    assert summary["priority_population_count"] == 215
    assert summary["existing_filing_route_validation_count"] == 4
    assert (
        summary["filing_route_discovery_required_count"]
        == 211
    )
    assert summary["reference_only_blocked_count"] == 1
    assert summary["network_capture_authorized"] is False
    assert summary["taxonomy_normalization_authorized"] is False
