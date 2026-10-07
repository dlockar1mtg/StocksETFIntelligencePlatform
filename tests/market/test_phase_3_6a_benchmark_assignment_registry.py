from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from foundation.market.benchmark_assignment_registry import assign_benchmark, build_assignment_registry

ROOT = Path(__file__).resolve().parents[2]


class Phase36ABenchmarkAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads((ROOT / "config/market/benchmark_assignment_registry_policy.json").read_text(encoding="utf-8"))
        self.registry = json.loads((ROOT / "config/market/benchmark_assignment_rules.json").read_text(encoding="utf-8"))
        self.record = {
            "security_id": "US-ETF-VOO", "symbol": "VOO", "asset_class": "EQUITY",
            "strategy": "BROAD_MARKET", "geography": "UNITED_STATES", "market_segment": "LARGE_CAP",
            "specialized_product_type": "NONE", "classification_status": "CLASSIFIED",
            "source_id": "ISSUER-PROSPECTUS", "source_record_id": "VOO-2026", "content_sha256": "a" * 64,
        }

    def test_states_are_exact(self):
        self.assertEqual(self.policy["assignment_states"], ["BENCHMARK_ASSIGNED", "BENCHMARK_UNASSIGNED", "BENCHMARK_UNSUPPORTED", "BENCHMARK_CONFLICTED"])

    def test_standard_taxonomy_assigns_stable_benchmark(self):
        result = assign_benchmark(self.record, self.registry, self.policy)
        self.assertEqual(result["assignment_state"], "BENCHMARK_ASSIGNED")
        self.assertEqual(result["benchmark_security_id"], "US-ETF-SPY")

    def test_unknown_rule_is_preserved_unassigned(self):
        record = copy.deepcopy(self.record); record["market_segment"] = "MICRO_CAP"
        self.assertEqual(assign_benchmark(record, self.registry, self.policy)["assignment_state"], "BENCHMARK_UNASSIGNED")

    def test_specialized_product_is_unsupported(self):
        record = copy.deepcopy(self.record); record["specialized_product_type"] = "LEVERAGED"
        self.assertEqual(assign_benchmark(record, self.registry, self.policy)["assignment_state"], "BENCHMARK_UNSUPPORTED")

    def test_conflicted_taxonomy_is_preserved(self):
        record = copy.deepcopy(self.record); record["classification_status"] = "CONFLICTED"
        self.assertEqual(assign_benchmark(record, self.registry, self.policy)["assignment_state"], "BENCHMARK_CONFLICTED")

    def test_multiple_rules_are_conflicted(self):
        registry = copy.deepcopy(self.registry)
        key = "EQUITY|BROAD_MARKET|UNITED_STATES|LARGE_CAP"
        registry["assignments"][key].append(copy.deepcopy(registry["assignments"][key][0]))
        self.assertEqual(assign_benchmark(self.record, registry, self.policy)["assignment_state"], "BENCHMARK_CONFLICTED")

    def test_self_benchmark_is_conflicted(self):
        registry = copy.deepcopy(self.registry)
        registry["assignments"]["EQUITY|BROAD_MARKET|UNITED_STATES|LARGE_CAP"][0]["benchmark_security_id"] = "US-ETF-VOO"
        self.assertEqual(assign_benchmark(self.record, registry, self.policy)["assignment_state"], "BENCHMARK_CONFLICTED")

    def test_missing_security_identity_fails_closed(self):
        record = copy.deepcopy(self.record); record.pop("security_id")
        with self.assertRaises(ValueError):
            assign_benchmark(record, self.registry, self.policy)

    def test_universe_rejects_count_drift(self):
        with self.assertRaises(ValueError):
            build_assignment_registry([self.record], self.registry, self.policy)

    def test_downstream_authority_remains_false(self):
        forbidden = ["relative_return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
        self.assertTrue(all(self.policy["authority"][item] is False for item in forbidden))


if __name__ == "__main__":
    unittest.main()
