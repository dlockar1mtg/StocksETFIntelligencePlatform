from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.full_universe_benchmark_assignment import (
    FullUniverseBenchmarkAssignmentError,
    build_full_universe_assignment,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase36BFullUniverseBenchmarkAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads((ROOT / "config/market/full_universe_benchmark_assignment_policy.json").read_text(encoding="utf-8"))
        self.policy["required_record_count"] = 4
        self.registry_policy = json.loads((ROOT / "config/market/benchmark_assignment_registry_policy.json").read_text(encoding="utf-8"))
        self.rules = {
            "assignments": {
                "EQUITY|BROAD_MARKET|UNITED_STATES|LARGE_CAP": [{
                    "benchmark_class": "US_LARGE_CAP_EQUITY",
                    "benchmark_security_id": "US-ETF-VOO",
                    "benchmark_symbol": "VOO"
                }]
            }
        }
        self.taxonomy = [
            self.tax("US-ETF-A", "A"),
            self.tax("US-ETF-B", "B", strategy="VALUE"),
            self.tax("US-ETF-C", "C", specialized="LEVERAGED"),
            self.tax("US-ETF-D", "D", status="CONFLICTED"),
        ]
        self.returns = [
            {"security_id": "US-ETF-A", "symbol": "A", "calculation_state": "CALCULATED"},
            {"security_id": "US-ETF-B", "symbol": "B", "calculation_state": "CALCULATED"},
            {"security_id": "US-ETF-C", "symbol": "C", "calculation_state": "CALCULATED"},
            {"security_id": "US-ETF-D", "symbol": "D", "calculation_state": "CALCULATION_BLOCKED"},
        ]

    def tax(self, security_id: str, symbol: str, strategy: str = "BROAD_MARKET", specialized: str = "NONE", status: str = "CLASSIFIED") -> dict:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "asset_class": "EQUITY",
            "strategy": strategy,
            "geography": "UNITED_STATES",
            "market_segment": "LARGE_CAP",
            "specialized_product_type": specialized,
            "classification_status": status,
            "source_id": "TEST",
            "source_record_id": symbol,
            "content_sha256": "a" * 64,
        }

    def build(self):
        return build_full_universe_assignment(self.taxonomy, self.returns, self.policy, self.registry_policy, self.rules)

    def test_all_records_are_preserved(self):
        result = self.build()
        self.assertEqual(result["record_count"], 4)
        self.assertEqual(len(result["assignments"]), 4)

    def test_all_four_assignment_states_are_reported(self):
        result = self.build()
        self.assertEqual(result["assignment_state_counts"], {
            "BENCHMARK_ASSIGNED": 1,
            "BENCHMARK_CONFLICTED": 1,
            "BENCHMARK_UNASSIGNED": 1,
            "BENCHMARK_UNSUPPORTED": 1,
        })

    def test_only_assigned_calculated_record_advances(self):
        result = self.build()
        self.assertEqual(result["active_analytical_candidate_count"], 1)
        self.assertEqual(result["active_analytical_candidates"][0]["security_id"], "US-ETF-A")

    def test_nonadvancing_records_are_preserved_excluded(self):
        result = self.build()
        excluded = [item for item in result["assignments"] if not item["active_analytical_candidate"]]
        self.assertEqual(len(excluded), 3)
        self.assertTrue(all(item["processing_treatment"] == "PRESERVE_EXCLUDE" for item in excluded))

    def test_identity_mismatch_fails_closed(self):
        returns = copy.deepcopy(self.returns)
        returns[-1]["security_id"] = "US-ETF-X"
        with self.assertRaises(FullUniverseBenchmarkAssignmentError):
            build_full_universe_assignment(self.taxonomy, returns, self.policy, self.registry_policy, self.rules)

    def test_count_drift_fails_closed(self):
        with self.assertRaises(FullUniverseBenchmarkAssignmentError):
            build_full_universe_assignment(self.taxonomy[:-1], self.returns, self.policy, self.registry_policy, self.rules)

    def test_duplicate_identity_fails_closed(self):
        taxonomy = copy.deepcopy(self.taxonomy)
        taxonomy[-1]["security_id"] = taxonomy[0]["security_id"]
        with self.assertRaises(FullUniverseBenchmarkAssignmentError):
            build_full_universe_assignment(taxonomy, self.returns, self.policy, self.registry_policy, self.rules)

    def test_candidate_publication_remains_review_only(self):
        result = self.build()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_outputs(result, root / "output.json", root / "summary.json", root / "candidates.json")
            candidates = json.loads((root / "candidates.json").read_text(encoding="utf-8"))
        self.assertEqual(candidates["publication_status"], "REVIEW_ONLY_NOT_CERTIFIED")

    def test_decision_authorities_remain_false(self):
        authority = self.policy["authority"]
        for key in ("benchmark_qualified_universe_publication", "relative_return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"):
            self.assertFalse(authority[key])


if __name__ == "__main__":
    unittest.main()
