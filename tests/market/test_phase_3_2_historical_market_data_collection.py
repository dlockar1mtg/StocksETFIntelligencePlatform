from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from foundation.infrastructure.historical_market_data import build_url, parse_historical_payload

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "sources" / "historical_market_data_collection_policy.json"


class Phase32HistoricalCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def payload(self, provider_symbol: str = "VOO", granularity: str = "1d") -> bytes:
        return json.dumps({"chart": {"error": None, "result": [{
            "meta": {"symbol": provider_symbol, "dataGranularity": granularity},
            "timestamp": [1609459200, 1609545600],
            "indicators": {"quote": [{"close": [100.0, 101.0]}], "adjclose": [{"adjclose": [99.0, 100.0]}]},
            "events": {"dividends": {"1": {"amount": 1.0}}, "splits": {}}
        }]}}).encode("utf-8")

    def test_policy_locks_candidate_count(self):
        self.assertEqual(self.policy["required_candidate_count"], 3462)

    def test_provisional_candidates_are_blocked(self):
        self.assertFalse(self.policy["provisional_candidates_allowed"])

    def test_pilot_is_required_before_full_collection(self):
        self.assertTrue(self.policy["pilot"]["required"])
        self.assertFalse(self.policy["pilot"]["full_universe_collection_authorized_before_pilot_review"])

    def test_required_seed_symbols_are_exact(self):
        self.assertEqual(self.policy["pilot"]["symbols"], ["VOO", "SCHD", "QQQM"])

    def test_build_url_uses_full_history_parameters(self):
        url = build_url("VOO", self.policy)
        self.assertIn("period1=0", url)
        self.assertIn("period2=2147483647", url)
        self.assertIn("interval=1d", url)
        self.assertIn("includeAdjustedClose=true", url)
        self.assertNotIn("range=", url)

    def test_valid_payload_is_normalized(self):
        payload = self.payload()
        record = parse_historical_payload(payload, security_id="sec-1", requested_symbol="VOO", source_url="u", raw_path="r", retrieved_at_utc="2026-08-04T00:00:00Z")
        self.assertEqual(record["collection_status"], "COLLECTED")
        self.assertEqual(record["provider_data_granularity"], "1d")
        self.assertEqual(record["observation_count"], 2)
        self.assertEqual(record["adjusted_price_observation_count"], 2)
        self.assertEqual(record["dividend_event_count"], 1)

    def test_lineage_hash_matches_payload(self):
        payload = self.payload()
        record = parse_historical_payload(payload, security_id="sec-1", requested_symbol="VOO", source_url="u", raw_path="r", retrieved_at_utc="2026-08-04T00:00:00Z")
        self.assertEqual(record["payload_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(record["source_lineage"]["payload_sha256"], record["payload_sha256"])

    def test_symbol_mismatch_is_explicit(self):
        record = parse_historical_payload(self.payload("SPY"), security_id="sec-1", requested_symbol="VOO", source_url="u", raw_path="r", retrieved_at_utc="2026-08-04T00:00:00Z")
        self.assertEqual(record["collection_status"], "SYMBOL_MISMATCH")

    def test_not_found_is_preserved(self):
        payload = json.dumps({"chart": {"error": None, "result": []}}).encode()
        record = parse_historical_payload(payload, security_id="sec-1", requested_symbol="VOO", source_url="u", raw_path="r", retrieved_at_utc="2026-08-04T00:00:00Z")
        self.assertEqual(record["collection_status"], "NOT_FOUND")

    def test_provider_error_is_preserved(self):
        payload = json.dumps({"chart": {"error": {"code": "x"}, "result": None}}).encode()
        record = parse_historical_payload(payload, security_id="sec-1", requested_symbol="VOO", source_url="u", raw_path="r", retrieved_at_utc="2026-08-04T00:00:00Z")
        self.assertEqual(record["collection_status"], "PROVIDER_ERROR")

    def test_downstream_authority_remains_false(self):
        forbidden = ["return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
        self.assertTrue(all(self.policy["authority"][key] is False for key in forbidden))

    def test_policy_is_fail_closed_and_resumable(self):
        self.assertTrue(self.policy["fail_closed"])
        self.assertTrue(self.policy["checkpoint_required"])
        self.assertTrue(self.policy["resumable"])
        self.assertTrue(self.policy["raw_payloads_immutable"])
        mismatch = parse_historical_payload(self.payload(granularity="1mo"), security_id="sec-1", requested_symbol="VOO", source_url="u", raw_path="r", retrieved_at_utc="2026-08-04T00:00:00Z")
        self.assertEqual(mismatch["collection_status"], "GRANULARITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
