from __future__ import annotations

import hashlib
import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from foundation.market.market_data_eligibility import (
    MarketDataEligibilityError,
    build_screen_input,
    classify_record,
    classify_universe,
    load_policy,
)


def payload(symbol: str = "VOO", count: int = 252, null_close: bool = False, conflicted_events: bool = False) -> bytes:
    start = int(datetime(2025, 8, 4, tzinfo=timezone.utc).timestamp())
    timestamps = [start + index * 86400 for index in range(count)]
    closes = [100.0 + index for index in range(count)]
    if null_close:
        closes[-1] = None
    events = {"dividends": {}, "splits": {}}
    if conflicted_events:
        events["splits"] = []
    document = {
        "chart": {
            "error": None,
            "result": [{
                "meta": {"symbol": symbol},
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{"close": closes, "volume": [1000000] * count}],
                    "adjclose": [{"adjclose": [100.0] * count}],
                },
                "events": events,
            }],
        }
    }
    return json.dumps(document).encode("utf-8")


def record(raw: bytes, symbol: str = "VOO", status: str = "COLLECTED") -> dict:
    document = json.loads(raw)
    timestamps = document["chart"]["result"][0]["timestamp"]
    closes = document["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    valid = [i for i, value in enumerate(closes) if value is not None]
    latest = datetime.fromtimestamp(timestamps[valid[-1]], tz=timezone.utc).date().isoformat()
    return {
        "security_id": f"SEC-US-{symbol}",
        "symbol": symbol,
        "provider_id": "YAHOO_FINANCE_CHART",
        "provider_symbol": symbol,
        "collection_status": status,
        "retrieved_at_utc": "2026-08-04T10:00:00Z",
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "observation_count": len(valid),
        "latest_observation_date": latest,
        "adjusted_price_available": True,
        "volume_observation_count": len(valid),
        "median_daily_dollar_volume": 100000000.0,
        "zero_volume_ratio": 0.0,
        "source_lineage": {"source_url": "https://example.test", "raw_path": f"{symbol}.json", "payload_sha256": hashlib.sha256(raw).hexdigest()},
    }


class Phase2B4EligibilityTests(unittest.TestCase):
    def test_policy_is_evidence_sized_and_fail_closed(self):
        policy = load_policy()
        self.assertEqual(policy["required_input_record_count"], 4419)
        self.assertIsNone(policy["target_universe_size"])
        self.assertTrue(policy["fail_closed"])

    def test_policy_grants_no_downstream_authority(self):
        authority = load_policy()["authority"]
        for key in ("full_history_collection", "analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"):
            self.assertFalse(authority[key])

    def test_valid_collected_record_is_eligible(self):
        raw = payload()
        item = record(raw)
        operating = date.fromisoformat(item["latest_observation_date"])
        result = classify_record(item, operating_date=operating, raw_payload=raw)
        self.assertEqual(result["screen_state"], "MARKET_DATA_ELIGIBLE")

    def test_limited_history_is_provisional(self):
        raw = payload(count=100)
        item = record(raw)
        operating = date.fromisoformat(item["latest_observation_date"])
        result = classify_record(item, operating_date=operating, raw_payload=raw)
        self.assertEqual(result["screen_state"], "MARKET_DATA_PROVISIONAL")

    def test_short_history_is_research_only(self):
        raw = payload(count=20)
        item = record(raw)
        operating = date.fromisoformat(item["latest_observation_date"])
        result = classify_record(item, operating_date=operating, raw_payload=raw)
        self.assertEqual(result["screen_state"], "RESEARCH_ONLY")

    def test_null_close_reduces_session_coverage(self):
        raw = payload(null_close=True)
        item = record(raw)
        operating = date.fromisoformat(item["latest_observation_date"])
        evidence = build_screen_input(item, raw_payload=raw, operating_date=operating)
        self.assertLess(evidence["expected_session_coverage_ratio"], 1.0)

    def test_payload_hash_mismatch_fails_closed(self):
        raw = payload()
        item = record(raw)
        item["payload_sha256"] = "0" * 64
        with self.assertRaises(MarketDataEligibilityError):
            build_screen_input(item, raw_payload=raw, operating_date=date(2026, 8, 4))

    def test_symbol_mismatch_fails_closed(self):
        raw = payload(symbol="SCHD")
        item = record(raw, symbol="VOO")
        with self.assertRaises(MarketDataEligibilityError):
            build_screen_input(item, raw_payload=raw, operating_date=date(2026, 8, 4))

    def test_non_collected_status_maps_without_deletion(self):
        raw = payload()
        item = record(raw, status="NOT_FOUND")
        result = classify_record(item, operating_date=date(2026, 8, 4))
        self.assertEqual(result["screen_state"], "BLOCKED")
        self.assertEqual(result["security_id"], item["security_id"])

    def test_unknown_collection_status_fails_closed(self):
        raw = payload()
        item = record(raw, status="MYSTERY")
        with self.assertRaises(MarketDataEligibilityError):
            classify_record(item, operating_date=date(2026, 8, 4))

    def test_duplicate_identity_fails_closed(self):
        raw = payload()
        item = record(raw)
        records = [dict(item) for _ in range(4419)]
        with TemporaryDirectory() as temp:
            Path(temp, "VOO.json").write_bytes(raw)
            with self.assertRaises(MarketDataEligibilityError):
                classify_universe(records, operating_date=date.fromisoformat(item["latest_observation_date"]), raw_root=Path(temp))

    def test_input_count_mismatch_fails_closed(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(MarketDataEligibilityError):
                classify_universe([], operating_date=date(2026, 8, 4), raw_root=Path(temp))


if __name__ == "__main__":
    unittest.main()
