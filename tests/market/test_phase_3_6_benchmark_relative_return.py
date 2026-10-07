from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.market.benchmark_relative_return import compare_horizon, compare_record

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "benchmark_relative_return_policy.json"


class Phase36BenchmarkRelativeReturnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def result(self, value: float, start: str = "2026-01-01", end: str = "2026-02-01") -> dict:
        return {
            "calculation_state": "CALCULATED",
            "return_basis": "ADJUSTED_CLOSE_TOTAL_RETURN",
            "start_date": start,
            "end_date": end,
            "cumulative_total_return": value,
        }

    def record(self, security_id: str, symbol: str, value: float) -> dict:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "horizons": {h: self.result(value) for h in self.policy["uip_horizon_contract"]},
        }

    def test_uip_horizons_are_exact(self):
        self.assertEqual(self.policy["uip_horizon_contract"], ["30d", "90d", "180d", "1y", "3y", "5y"])

    def test_excess_return_is_asset_minus_benchmark(self):
        result = compare_horizon(asset_result=self.result(0.12), benchmark_result=self.result(0.08), horizon="30d", required_return_basis="ADJUSTED_CLOSE_TOTAL_RETURN")
        self.assertAlmostEqual(result["excess_total_return"], 0.04)

    def test_start_date_mismatch_blocks(self):
        result = compare_horizon(asset_result=self.result(0.12), benchmark_result=self.result(0.08, start="2026-01-02"), horizon="30d", required_return_basis="ADJUSTED_CLOSE_TOTAL_RETURN")
        self.assertEqual(result["comparison_state"], "RELATIVE_RETURN_BLOCKED")

    def test_missing_assignment_is_preserved(self):
        result = compare_record(self.record("A", "AAA", 0.1), benchmark_record=None, assignment=None, policy=self.policy)
        self.assertEqual(result["benchmark_state"], "BENCHMARK_UNASSIGNED")
        self.assertFalse(result["authority"]["relative_return_calculation"])

    def test_missing_benchmark_record_is_unsupported(self):
        assignment = {"benchmark_security_id": "B", "benchmark_class": "US_BROAD_MARKET", "taxonomy_evidence": {"source": "test"}}
        result = compare_record(self.record("A", "AAA", 0.1), benchmark_record=None, assignment=assignment, policy=self.policy)
        self.assertEqual(result["benchmark_state"], "BENCHMARK_UNSUPPORTED")

    def test_self_benchmark_is_blocked(self):
        assignment = {"benchmark_security_id": "A", "benchmark_class": "US_BROAD_MARKET", "taxonomy_evidence": {"source": "test"}}
        result = compare_record(self.record("A", "AAA", 0.1), benchmark_record=self.record("A", "AAA", 0.1), assignment=assignment, policy=self.policy)
        self.assertEqual(result["benchmark_state"], "BENCHMARK_BLOCKED")

    def test_valid_assignment_calculates_all_horizons(self):
        assignment = {"benchmark_security_id": "B", "benchmark_class": "US_BROAD_MARKET", "taxonomy_evidence": {"source": "test"}}
        result = compare_record(self.record("A", "AAA", 0.1), benchmark_record=self.record("B", "BBB", 0.04), assignment=assignment, policy=self.policy)
        self.assertEqual(result["benchmark_state"], "BENCHMARK_ASSIGNED")
        self.assertTrue(all(v["comparison_state"] == "RELATIVE_RETURN_CALCULATED" for v in result["horizons"].values()))

    def test_decision_authorities_remain_false(self):
        forbidden = ["risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
        self.assertTrue(all(self.policy["authority"][key] is False for key in forbidden))


if __name__ == "__main__":
    unittest.main()
