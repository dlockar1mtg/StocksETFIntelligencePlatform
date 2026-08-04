from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

from foundation.market.market_data_screen import (
    MarketDataScreenError,
    load_policy,
    screen_record,
    screen_universe,
)

ROOT = Path(__file__).resolve().parents[2]


def valid_record(symbol: str = "VOO", security_id: str = "SEC-US-VOO") -> dict:
    return {
        "security_id": security_id,
        "symbol": symbol,
        "processing_state": "ACTIVE_STRUCTURAL_UNIVERSE",
        "observation_start_date": "2025-07-31",
        "observation_end_date": "2026-08-03",
        "price_observation_count": 252,
        "expected_trading_session_count": 252,
        "expected_session_coverage_ratio": 1.0,
        "latest_observation_age_calendar_days": 0,
        "adjusted_price_available": True,
        "median_daily_dollar_volume_usd": 1000000.0,
        "zero_volume_session_ratio": 0.0,
        "corporate_action_conflict_state": "CLEAR",
        "source_lineage": {
            "source_id": "TEST_MARKET_PROVIDER",
            "retrieved_at_utc": "2026-08-04T03:00:00Z",
            "content_sha256": "a" * 64,
        },
    }


class Phase2B1MarketDataScreenTests(unittest.TestCase):
    def test_policy_is_evidence_sized_and_non_destructive(self) -> None:
        policy = load_policy()
        self.assertEqual(policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")
        self.assertIsNone(policy["target_universe_size"])
        self.assertTrue(policy["preserve_input_universe"])
        self.assertFalse(policy["destructive_deletion_allowed"])

    def test_contract_is_registered(self) -> None:
        registry = json.loads((ROOT / "config/contracts/contract_registry.json").read_text())
        ids = {item["contract_id"] for item in registry["contracts"]}
        self.assertIn("native.etf_market_data_screen_record", ids)

    def test_valid_record_is_market_data_eligible(self) -> None:
        result = screen_record(valid_record(), date(2026, 8, 3))
        self.assertEqual(result["screen_state"], "MARKET_DATA_ELIGIBLE")
        self.assertFalse(result["analytics_authorized"])
        self.assertFalse(result["forecasting_authorized"])

    def test_limited_history_is_provisional(self) -> None:
        record = valid_record()
        record["price_observation_count"] = 100
        record["expected_trading_session_count"] = 100
        result = screen_record(record, date(2026, 8, 3))
        self.assertEqual(result["screen_state"], "MARKET_DATA_PROVISIONAL")

    def test_insufficient_history_is_research_only(self) -> None:
        record = valid_record()
        record["price_observation_count"] = 20
        record["expected_trading_session_count"] = 20
        result = screen_record(record, date(2026, 8, 3))
        self.assertEqual(result["screen_state"], "RESEARCH_ONLY")

    def test_stale_data_is_research_only(self) -> None:
        record = valid_record()
        record["observation_end_date"] = "2026-07-20"
        record["latest_observation_age_calendar_days"] = 14
        result = screen_record(record, date(2026, 8, 3))
        self.assertEqual(result["screen_state"], "RESEARCH_ONLY")
        self.assertIn("STALE_MARKET_DATA", result["screen_reasons"])

    def test_missing_adjusted_price_is_research_only(self) -> None:
        record = valid_record()
        record["adjusted_price_available"] = False
        result = screen_record(record, date(2026, 8, 3))
        self.assertEqual(result["screen_state"], "RESEARCH_ONLY")

    def test_critical_corporate_action_conflict_is_quarantined(self) -> None:
        record = valid_record()
        record["corporate_action_conflict_state"] = "CRITICAL"
        result = screen_record(record, date(2026, 8, 3))
        self.assertEqual(result["screen_state"], "QUARANTINED")

    def test_missing_required_evidence_fails_closed(self) -> None:
        record = valid_record()
        del record["source_lineage"]
        with self.assertRaises(MarketDataScreenError):
            screen_record(record, date(2026, 8, 3))

    def test_future_observation_fails_closed(self) -> None:
        record = valid_record()
        record["observation_end_date"] = "2026-08-04"
        record["latest_observation_age_calendar_days"] = -1
        with self.assertRaises(MarketDataScreenError):
            screen_record(record, date(2026, 8, 3))

    def test_coverage_mismatch_fails_closed(self) -> None:
        record = valid_record()
        record["expected_session_coverage_ratio"] = 0.75
        with self.assertRaises(MarketDataScreenError):
            screen_record(record, date(2026, 8, 3))

    def test_universe_requires_seeds_and_unique_identity(self) -> None:
        records = [
            valid_record("VOO", "SEC-US-VOO"),
            valid_record("SCHD", "SEC-US-SCHD"),
            valid_record("QQQM", "SEC-US-QQQM"),
        ]
        result = screen_universe(records, date(2026, 8, 3))
        self.assertEqual(result["total_input_records"], 3)
        self.assertTrue(result["input_universe_preserved"])
        duplicate = deepcopy(records)
        duplicate.append(deepcopy(records[0]))
        with self.assertRaises(MarketDataScreenError):
            screen_universe(duplicate, date(2026, 8, 3))


if __name__ == "__main__":
    unittest.main()
