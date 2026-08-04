from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.total_return_calculation import calculate_horizon, calculate_record, calculate_universe

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "total_return_calculation_policy.json"
EXPECTED_HORIZONS = {"30d": 21, "90d": 63, "180d": 126, "1y": 252, "3y": 756, "5y": 1260}


class Phase35TotalReturnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def payload(self, count: int = 1260) -> bytes:
        start = 1609459200
        timestamps = [start + i * 86400 for i in range(count)]
        adjusted = [100.0 + i for i in range(count)]
        return json.dumps({"chart": {"error": None, "result": [{"timestamp": timestamps, "indicators": {"adjclose": [{"adjclose": adjusted}]}}]}}).encode("utf-8")

    def certification_record(self, payload: bytes, count: int = 1260) -> dict:
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "security_id": "sec-VOO", "symbol": "VOO", "evidence_state": "EVIDENCE_CERTIFIED",
            "source_payload_sha256": digest,
            "eligible_horizons": {
                "30d": count >= 21, "90d": count >= 63, "180d": count >= 126,
                "1y": count >= 252, "3y": count >= 756, "5y": count >= 1260,
            },
        }

    def test_policy_locks_total_return_basis(self):
        self.assertEqual(self.policy["return_basis"], "ADJUSTED_CLOSE_TOTAL_RETURN")

    def test_horizon_thresholds_match_phase_3_4(self):
        self.assertEqual(self.policy["horizon_minimum_observations"], EXPECTED_HORIZONS)

    def test_interpolation_and_imputation_are_forbidden(self):
        window = self.policy["window_selection"]
        self.assertFalse(window["interpolation_allowed"])
        self.assertFalse(window["silent_imputation_allowed"])

    def test_simple_total_return_is_exact(self):
        result = calculate_horizon(series=[("2026-01-01", 100.0), ("2026-01-02", 110.0)], horizon="30d", minimum_observations=2, annualized=False, day_basis=365.2425)
        self.assertAlmostEqual(result["cumulative_total_return"], 0.10)
        self.assertIsNone(result["annualized_total_return"])

    def test_multiyear_return_is_annualized(self):
        result = calculate_horizon(series=[("2020-01-01", 100.0), ("2023-01-01", 133.1)], horizon="3y", minimum_observations=2, annualized=True, day_basis=365.2425)
        self.assertIsNotNone(result["annualized_total_return"])

    def test_horizon_uses_last_n_observations(self):
        series = [(f"2026-01-{i:02d}", float(i)) for i in range(1, 22)]
        result = calculate_horizon(series=series, horizon="30d", minimum_observations=21, annualized=False, day_basis=365.2425)
        self.assertEqual(result["start_adjusted_price"], 1.0)
        self.assertEqual(result["end_adjusted_price"], 21.0)

    def test_ineligible_horizon_is_not_calculated(self):
        payload = self.payload(count=252); record = self.certification_record(payload, count=252)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "sec-VOO.json").write_bytes(payload)
            result = calculate_record(record, raw_root=root, policy=self.policy)
        self.assertEqual(result["horizons"]["3y"]["calculation_state"], "NOT_AUTHORIZED")

    def test_hash_mismatch_fails_closed(self):
        payload = self.payload(); record = self.certification_record(payload); record["source_payload_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "sec-VOO.json").write_bytes(payload)
            with self.assertRaises(ValueError): calculate_record(record, raw_root=root, policy=self.policy)

    def test_nonpositive_adjusted_price_is_preserved_and_blocked(self):
        document = json.loads(self.payload().decode("utf-8")); document["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][-1] = 0
        payload = json.dumps(document).encode("utf-8"); record = self.certification_record(payload)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "sec-VOO.json").write_bytes(payload); result = calculate_record(record, raw_root=root, policy=self.policy)
        self.assertEqual(result["calculation_state"], "CALCULATION_BLOCKED")
        self.assertTrue(all(item["calculation_state"] == "CALCULATION_BLOCKED" for item in result["horizons"].values()))
        self.assertFalse(result["authority"]["return_calculation"])

    def test_universe_rejects_duplicate_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError): calculate_universe({"records": [{"security_id": "x"}] * 3462}, raw_root=Path(temp), policy=self.policy)

    def test_return_authority_only_expands_to_calculation(self):
        self.assertTrue(self.policy["authority"]["return_calculation"])
        forbidden = ["risk_analytics", "benchmark_comparison", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
        self.assertTrue(all(self.policy["authority"][key] is False for key in forbidden))

    def test_record_preserves_lineage_and_blocks_decision_authority(self):
        payload = self.payload(); record = self.certification_record(payload)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "sec-VOO.json").write_bytes(payload); result = calculate_record(record, raw_root=root, policy=self.policy)
        self.assertEqual(result["source_payload_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertFalse(result["authority"]["ranking"])
        self.assertFalse(result["authority"]["recommendations"])


if __name__ == "__main__":
    unittest.main()
