from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timezone

from foundation.infrastructure.structural_metadata import (
    StructuralMetadataError,
    classify_specialized_flags,
    load_policy,
    normalize_record,
    reconcile_records,
    summarize_coverage,
    validate_policy,
    validate_record,
)

NOW = datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc)


def lineage(source_id: str = "ISSUER", digest: str = "a" * 64) -> list[dict]:
    return [{
        "source_id": source_id,
        "dataset_id": "ETF_PROFILE",
        "source_record_id": "VOO",
        "retrieved_at_utc": "2026-08-04T03:00:00Z",
        "observed_at_utc": "2026-08-04T02:59:00Z",
        "authority_level": "PRIMARY_OFFICIAL",
        "source_status": "certified",
        "license_class": "PUBLIC_OFFICIAL",
        "content_sha256": digest,
    }]


def raw_record() -> dict:
    return {
        "security_id": "SEC-US-VOO",
        "symbol": "VOO",
        "fund_name": "Vanguard S&P 500 ETF",
        "issuer_name": "Vanguard",
        "instrument_structure": "ETF",
        "fund_status": "ACTIVE",
        "inception_date": "2010-09-07",
        "strategy_description": "Tracks the S&P 500 Index",
        "benchmark_name": "S&P 500 Index",
        "expense_ratio": 0.0003,
        "aum_usd": 500000000000.0,
    }


class Phase2A2StructuralMetadataTests(unittest.TestCase):
    def test_policy_is_evidence_sized_and_fail_closed(self) -> None:
        policy = load_policy()
        self.assertIsNone(policy["target_universe_size"])
        self.assertEqual(policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")
        self.assertTrue(policy["preserve_full_discovery_universe"])
        self.assertTrue(policy["raw_evidence_immutable"])
        self.assertTrue(policy["fail_closed"])

    def test_policy_grants_no_downstream_authority(self) -> None:
        policy = load_policy()
        for name in (
            "production_data_certification", "analytics_production", "forecasting", "ranking",
            "recommendations", "portfolio_allocation", "uip_export", "automatic_execution",
            "direct_uip_database_writes",
        ):
            self.assertFalse(policy["authority"][name], name)

    def test_arbitrary_universe_target_is_rejected(self) -> None:
        policy = deepcopy(load_policy())
        policy["target_universe_size"] = 100
        with self.assertRaises(StructuralMetadataError):
            validate_policy(policy)

    def test_standard_etf_normalizes_complete(self) -> None:
        record = normalize_record(raw_record(), lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        self.assertEqual(record["record_status"], "COMPLETE")
        self.assertEqual(record["specialized_flags"], [])
        validate_record(record, NOW)

    def test_empty_specialized_flags_are_valid(self) -> None:
        record = normalize_record(raw_record(), lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        self.assertEqual(record["specialized_flags"], [])

    def test_specialized_structure_is_detected_from_text(self) -> None:
        flags = classify_specialized_flags("Example 2x Bitcoin Strategy ETF", "Uses futures and swaps")
        self.assertIn("LEVERAGED", flags)
        self.assertIn("CRYPTO_LINKED", flags)
        self.assertIn("DERIVATIVE_HEAVY", flags)
        self.assertIn("COMMODITY_OR_FUTURES", flags)

    def test_missing_metadata_remains_partial_not_imputed(self) -> None:
        raw = raw_record()
        raw["issuer_name"] = None
        raw["inception_date"] = None
        record = normalize_record(raw, lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        self.assertEqual(record["record_status"], "PARTIAL")
        self.assertIsNone(record["issuer_name"])
        self.assertIsNone(record["inception_date"])

    def test_future_evidence_is_rejected(self) -> None:
        record = normalize_record(raw_record(), lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        record["observed_at_utc"] = "2026-08-05T00:00:00Z"
        with self.assertRaises(StructuralMetadataError):
            validate_record(record, NOW)

    def test_invalid_lineage_hash_is_rejected(self) -> None:
        with self.assertRaises(StructuralMetadataError):
            normalize_record(raw_record(), lineage(digest="bad"), "2026-08-04T03:00:00Z", "2026-08-03")

    def test_closing_fund_must_be_blocked(self) -> None:
        raw = raw_record()
        raw["fund_status"] = "CLOSING"
        record = normalize_record(raw, lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        with self.assertRaises(StructuralMetadataError):
            validate_record(record, NOW)
        record["record_status"] = "BLOCKED"
        validate_record(record, NOW)

    def test_conflicts_are_preserved_not_averaged(self) -> None:
        first = normalize_record(raw_record(), lineage("ISSUER"), "2026-08-04T03:00:00Z", "2026-08-03")
        second_raw = raw_record()
        second_raw["expense_ratio"] = 0.0004
        second = normalize_record(second_raw, lineage("STRUCTURED"), "2026-08-04T03:00:00Z", "2026-08-03")
        result = reconcile_records([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["record_status"], "CONFLICTED")
        self.assertIn("expense_ratio", result[0]["conflict_fields"])
        self.assertEqual(result[0]["expense_ratio"], 0.0003)

    def test_duplicate_identical_sources_reconcile_lineage(self) -> None:
        first = normalize_record(raw_record(), lineage("ISSUER"), "2026-08-04T03:00:00Z", "2026-08-03")
        second = normalize_record(raw_record(), lineage("SEC"), "2026-08-04T03:00:00Z", "2026-08-03")
        result = reconcile_records([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["source_lineage"]), 2)
        self.assertEqual(result[0]["conflict_fields"], [])

    def test_record_cannot_grant_analytics_authority(self) -> None:
        record = normalize_record(raw_record(), lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        record["authority"]["analytics_authorized"] = True
        with self.assertRaises(StructuralMetadataError):
            validate_record(record, NOW)

    def test_coverage_summary_reports_evidence_not_target(self) -> None:
        complete = normalize_record(raw_record(), lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        partial_raw = raw_record()
        partial_raw["security_id"] = "SEC-US-XYZ"
        partial_raw["symbol"] = "XYZ"
        partial_raw["issuer_name"] = None
        partial = normalize_record(partial_raw, lineage(), "2026-08-04T03:00:00Z", "2026-08-03")
        summary = summarize_coverage([complete, partial])
        self.assertEqual(summary["total_records"], 2)
        self.assertEqual(summary["record_status_counts"]["COMPLETE"], 1)
        self.assertEqual(summary["record_status_counts"]["PARTIAL"], 1)
        self.assertIsNone(summary["target_universe_size"])


if __name__ == "__main__":
    unittest.main()
