from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from foundation.universe.structural_triage import (
    StructuralTriageError,
    load_policy,
    summarize_records,
    validate_policy,
    validate_record,
)

NOW = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


def valid_record() -> dict:
    return {
        "security_id": "SEC-US-VOO",
        "symbol": "VOO",
        "broker_status": "ELIGIBLE",
        "instrument_structure": "ETF",
        "strategy_family": "US_LARGE_CAP_BLEND",
        "benchmark_id": "SP500",
        "issuer_id": "VANGUARD",
        "specialized_flags": [],
        "fund_status": "ACTIVE",
        "inception_date": "2010-09-07",
        "history_depth_days": 5800,
        "median_daily_dollar_volume": 500000000.0,
        "median_bid_ask_spread_bps": 1.0,
        "aum_usd": 500000000000.0,
        "expense_ratio": 0.0003,
        "holdings_transparency_status": "CURRENT",
        "liquidity_status": "PASS",
        "identity_quality_status": "PASS",
        "evidence_quality_status": "PASS",
        "conflict_status": "NONE",
        "triage_state": "DATA_COLLECTION_CANDIDATE",
        "reason_codes": ["STRUCTURE_ADMISSIBLE", "IDENTITY_COMPLETE"],
        "cost_tier": "TIER_2_MARKET_SCREEN",
        "observed_at_utc": "2026-08-04T02:00:00Z",
        "effective_date": "2026-08-03",
        "source_lineage": [
            {
                "source_id": "ISSUER",
                "dataset_id": "ETF_PROFILE",
                "source_record_id": "VOO",
                "retrieved_at_utc": "2026-08-04T02:00:00Z",
                "observed_at_utc": "2026-08-04T01:59:00Z",
                "effective_date": "2026-08-03",
                "revision_date": None,
                "authority_level": "PRIMARY_OFFICIAL",
                "source_status": "certified",
                "license_class": "PUBLIC_OFFICIAL",
                "content_sha256": "a" * 64,
            }
        ],
        "authority": {
            "analytics_authorized": False,
            "recommendations_authorized": False,
            "uip_export_authorized": False,
            "automatic_execution_authorized": False,
        },
    }


class Phase2AStructuralTriageTests(unittest.TestCase):
    def test_policy_has_no_target_universe_size(self) -> None:
        policy = load_policy()
        self.assertIsNone(policy["target_universe_size"])
        self.assertEqual(policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")

    def test_full_discovery_universe_is_preserved(self) -> None:
        policy = load_policy()
        self.assertTrue(policy["preserve_full_discovery_universe"])
        self.assertFalse(policy["destructive_deletion_allowed"])

    def test_policy_grants_no_downstream_authority(self) -> None:
        policy = load_policy()
        for name, value in policy["authority"].items():
            if name.endswith("development"):
                continue
            self.assertFalse(value, name)

    def test_valid_standard_etf_passes(self) -> None:
        validate_record(valid_record(), NOW)

    def test_empty_specialized_flags_are_valid_evidence(self) -> None:
        record = valid_record()
        self.assertEqual(record["specialized_flags"], [])
        validate_record(record, NOW)

    def test_missing_specialized_flags_fail_closed(self) -> None:
        record = valid_record()
        del record["specialized_flags"]
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)

    def test_certification_script_bootstraps_repository_imports(self) -> None:
        script = (ROOT / "scripts" / "certify_phase_2a_structural_triage.py").read_text(encoding="utf-8")
        path_insert = script.index("sys.path.insert")
        foundation_import = script.index("from foundation.universe.structural_triage import load_policy")
        self.assertLess(path_insert, foundation_import)

    def test_broker_ineligible_record_is_blocked(self) -> None:
        record = valid_record()
        record["broker_status"] = "SELL_ONLY"
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)
        record["triage_state"] = "BLOCKED"
        record["cost_tier"] = "TIER_0_REFERENCE"
        validate_record(record, NOW)

    def test_etn_requires_separate_approval(self) -> None:
        record = valid_record()
        record["instrument_structure"] = "ETN"
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)
        record["triage_state"] = "RESEARCH_ONLY"
        record["cost_tier"] = "TIER_0_REFERENCE"
        validate_record(record, NOW)

    def test_leveraged_fund_requires_specialized_treatment(self) -> None:
        record = valid_record()
        record["specialized_flags"] = ["LEVERAGED"]
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)
        record["triage_state"] = "SPECIALIZED"
        record["cost_tier"] = "TIER_1_STRUCTURAL"
        validate_record(record, NOW)

    def test_critical_conflict_blocks_promotion(self) -> None:
        record = valid_record()
        record["conflict_status"] = "UNRESOLVED_CRITICAL"
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)

    def test_blocked_evidence_cannot_support_promotion(self) -> None:
        record = valid_record()
        record["source_lineage"][0]["source_status"] = "blocked"
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)

    def test_future_evidence_is_rejected(self) -> None:
        record = valid_record()
        record["observed_at_utc"] = "2026-08-05T00:00:00Z"
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)

    def test_record_cannot_grant_analytics_or_recommendation_authority(self) -> None:
        record = valid_record()
        record["authority"]["analytics_authorized"] = True
        with self.assertRaises(StructuralTriageError):
            validate_record(record, NOW)

    def test_duplicate_security_identity_fails_closed(self) -> None:
        record = valid_record()
        with self.assertRaises(StructuralTriageError):
            summarize_records([record, deepcopy(record)])

    def test_summary_reports_evidence_derived_counts(self) -> None:
        first = valid_record()
        second = valid_record()
        second["security_id"] = "SEC-US-XYZ"
        second["symbol"] = "XYZ"
        second["specialized_flags"] = ["ACTIVE_MANAGEMENT"]
        second["triage_state"] = "SPECIALIZED"
        second["cost_tier"] = "TIER_1_STRUCTURAL"
        summary = summarize_records([first, second])
        self.assertEqual(summary.total_records, 2)
        self.assertEqual(summary.counts_by_state["DATA_COLLECTION_CANDIDATE"], 1)
        self.assertEqual(summary.counts_by_state["SPECIALIZED"], 1)
        self.assertIsNone(summary.target_universe_size)

    def test_policy_rejects_arbitrary_size_cap(self) -> None:
        policy = deepcopy(load_policy())
        policy["target_universe_size"] = 100
        with self.assertRaises(StructuralTriageError):
            validate_policy(policy)


if __name__ == "__main__":
    unittest.main()
