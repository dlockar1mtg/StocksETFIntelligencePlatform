from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from foundation.infrastructure.recent_market_data import build_url, parse_chart_payload


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config/sources/recent_market_data_acquisition_policy.json"
REGISTRY_PATH = ROOT / "config/contracts/contract_registry.json"
SCHEMA_PATH = ROOT / "contracts/native/recent_market_data_observation.schema.json"


def sample_payload(symbol: str = "VOO") -> bytes:
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": symbol},
                        "timestamp": [1767225600, 1767312000, 1767398400],
                        "indicators": {
                            "quote": [{"close": [100.0, 101.0, 102.0], "volume": [1000, 0, 2000]}],
                            "adjclose": [{"adjclose": [99.5, 100.5, 101.5]}],
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode("utf-8")


class Phase2B2RecentMarketDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_policy_is_fail_closed_and_evidence_sized(self) -> None:
        self.assertTrue(self.policy["fail_closed"])
        self.assertEqual(self.policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")
        self.assertIsNone(self.policy["target_universe_size"])
        self.assertTrue(self.policy["preserve_all_input_records"])

    def test_policy_grants_no_downstream_authority(self) -> None:
        authority = self.policy["authority"]
        self.assertTrue(authority["recent_market_data_collection"])
        for key in ("full_history_collection", "analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"):
            self.assertFalse(authority[key])

    def test_required_seeds_are_locked(self) -> None:
        self.assertEqual(self.policy["required_seed_symbols"], ["VOO", "SCHD", "QQQM"])

    def test_contract_is_registered(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        contracts = {item["contract_id"]: item for item in registry["contracts"]}
        self.assertIn("native.recent_market_data_observation", contracts)
        self.assertTrue(SCHEMA_PATH.exists())

    def test_build_url_uses_governed_parameters(self) -> None:
        url = build_url("VOO", self.policy)
        self.assertIn("VOO", url)
        self.assertIn("interval=1d", url)
        self.assertIn("range=18mo", url)
        self.assertIn("includeAdjustedClose=true", url)

    def test_invalid_symbol_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_url("VOO/../../", self.policy)

    def test_valid_payload_is_normalized(self) -> None:
        payload = sample_payload()
        record = parse_chart_payload(
            payload,
            security_id="SEC-US-VOO",
            requested_symbol="VOO",
            source_url="https://example.test/VOO",
            raw_path="data/raw/VOO.json",
            retrieved_at_utc="2026-08-04T03:00:00Z",
        )
        self.assertEqual(record["collection_status"], "COLLECTED")
        self.assertEqual(record["observation_count"], 3)
        self.assertTrue(record["adjusted_price_available"])
        self.assertEqual(record["volume_observation_count"], 3)
        self.assertAlmostEqual(record["zero_volume_ratio"], 1 / 3)
        self.assertEqual(record["payload_sha256"], hashlib.sha256(payload).hexdigest())

    def test_symbol_mismatch_is_explicit(self) -> None:
        record = parse_chart_payload(
            sample_payload("VOOG"),
            security_id="SEC-US-VOO",
            requested_symbol="VOO",
            source_url="https://example.test/VOO",
            raw_path="data/raw/VOO.json",
            retrieved_at_utc="2026-08-04T03:00:00Z",
        )
        self.assertEqual(record["collection_status"], "SYMBOL_MISMATCH")

    def test_not_found_is_preserved(self) -> None:
        payload = json.dumps({"chart": {"result": None, "error": None}}).encode("utf-8")
        record = parse_chart_payload(
            payload,
            security_id="SEC-US-XXXX",
            requested_symbol="XXXX",
            source_url="https://example.test/XXXX",
            raw_path="data/raw/XXXX.json",
            retrieved_at_utc="2026-08-04T03:00:00Z",
        )
        self.assertEqual(record["collection_status"], "NOT_FOUND")
        self.assertEqual(record["observation_count"], 0)

    def test_provider_error_is_preserved(self) -> None:
        payload = json.dumps({"chart": {"result": None, "error": {"code": "Bad Request"}}}).encode("utf-8")
        record = parse_chart_payload(
            payload,
            security_id="SEC-US-XXXX",
            requested_symbol="XXXX",
            source_url="https://example.test/XXXX",
            raw_path="data/raw/XXXX.json",
            retrieved_at_utc="2026-08-04T03:00:00Z",
        )
        self.assertEqual(record["collection_status"], "ERROR")

    def test_normalized_record_grants_no_forecasting_authority(self) -> None:
        record = parse_chart_payload(
            sample_payload(),
            security_id="SEC-US-VOO",
            requested_symbol="VOO",
            source_url="https://example.test/VOO",
            raw_path="data/raw/VOO.json",
            retrieved_at_utc="2026-08-04T03:00:00Z",
        )
        self.assertTrue(record["authority"]["market_screen"])
        self.assertFalse(record["authority"]["analytics"])
        self.assertFalse(record["authority"]["forecasting"])
        self.assertFalse(record["authority"]["recommendations"])
        self.assertFalse(record["authority"]["automatic_execution"])

    def test_lineage_hash_matches_payload_hash(self) -> None:
        record = parse_chart_payload(
            sample_payload(),
            security_id="SEC-US-VOO",
            requested_symbol="VOO",
            source_url="https://example.test/VOO",
            raw_path="data/raw/VOO.json",
            retrieved_at_utc="2026-08-04T03:00:00Z",
        )
        self.assertEqual(record["payload_sha256"], record["source_lineage"]["payload_sha256"])


if __name__ == "__main__":
    unittest.main()
