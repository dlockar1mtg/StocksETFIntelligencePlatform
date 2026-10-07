from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.full_historical_collection import build_completion_attestation, index_checkpoint, validate_candidate_universe, validate_pilot

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config" / "market" / "full_historical_collection_authorization_policy.json").read_text(encoding="utf-8"))


def candidate(symbol: str, security_id: str) -> dict:
    return {"symbol": symbol, "security_id": security_id, "screen_state": "MARKET_DATA_ELIGIBLE"}


def collected(symbol: str, security_id: str, observations: int = 300) -> dict:
    return {
        "symbol": symbol,
        "security_id": security_id,
        "collection_status": "COLLECTED",
        "provider_data_granularity": "1d",
        "observation_count": observations,
        "adjusted_price_observation_count": observations,
    }


class Phase33FullHistoricalCollectionTests(unittest.TestCase):
    def full_candidates(self):
        records = [candidate("VOO", "1"), candidate("SCHD", "2"), candidate("QQQM", "3")]
        records.extend(candidate(f"X{i}", str(i)) for i in range(4, 3463))
        return {"provisional_records_included": False, "records": records}

    def test_policy_authorizes_full_collection(self):
        self.assertTrue(POLICY["full_collection"]["authorized"])
        self.assertEqual(POLICY["full_collection"]["expected_record_count"], 3462)

    def test_provisional_candidates_remain_blocked(self):
        self.assertFalse(POLICY["provisional_candidates_allowed"])

    def test_downstream_authority_remains_false(self):
        forbidden = ["return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"]
        self.assertTrue(all(POLICY["authority"][key] is False for key in forbidden))

    def test_valid_candidate_universe_passes(self):
        self.assertEqual(len(validate_candidate_universe(self.full_candidates(), POLICY)), 3462)

    def test_candidate_count_drift_fails(self):
        doc = self.full_candidates(); doc["records"].pop()
        with self.assertRaises(ValueError): validate_candidate_universe(doc, POLICY)

    def test_duplicate_candidate_identity_fails(self):
        doc = self.full_candidates(); doc["records"][-1]["security_id"] = "1"
        with self.assertRaises(ValueError): validate_candidate_universe(doc, POLICY)

    def test_valid_pilot_passes(self):
        checkpoint = {"records": [collected("VOO", "1"), collected("SCHD", "2"), collected("QQQM", "3")]}
        self.assertEqual(validate_pilot(checkpoint, POLICY)["pilot_status"], "PASS")

    def test_nondaily_pilot_fails(self):
        records = [collected("VOO", "1"), collected("SCHD", "2"), collected("QQQM", "3")]
        records[0]["provider_data_granularity"] = "1mo"
        with self.assertRaises(ValueError): validate_pilot({"records": records}, POLICY)

    def test_incomplete_adjusted_coverage_fails(self):
        records = [collected("VOO", "1"), collected("SCHD", "2"), collected("QQQM", "3")]
        records[0]["adjusted_price_observation_count"] = 299
        with self.assertRaises(ValueError): validate_pilot({"records": records}, POLICY)

    def test_unknown_checkpoint_identity_fails(self):
        candidates = self.full_candidates()["records"]
        with self.assertRaises(ValueError): index_checkpoint({"records": [collected("VOO", "unknown")]}, candidates)

    def test_duplicate_checkpoint_identity_fails(self):
        candidates = self.full_candidates()["records"]
        record = collected("VOO", "1")
        with self.assertRaises(ValueError): index_checkpoint({"records": [record, record]}, candidates)

    def test_completion_attestation_requires_all_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / "c.json"; checkpoint_path = root / "k.json"; summary_path = root / "s.json"
            candidate_path.write_text(json.dumps(self.full_candidates()), encoding="utf-8")
            checkpoint_path.write_text(json.dumps({"records": [collected("VOO", "1"), collected("SCHD", "2"), collected("QQQM", "3")]}), encoding="utf-8")
            summary_path.write_text("{}", encoding="utf-8")
            result = build_completion_attestation(candidate_path=candidate_path, checkpoint_path=checkpoint_path, summary_path=summary_path, policy=POLICY)
            self.assertEqual(result["completion_status"], "PARTIAL")
            self.assertEqual(result["remaining_records"], 3459)


if __name__ == "__main__":
    unittest.main()
