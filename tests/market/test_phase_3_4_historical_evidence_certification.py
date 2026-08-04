from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.market.historical_evidence_certification import certify_record, certify_universe

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "historical_evidence_certification_policy.json"


class Phase34HistoricalEvidenceCertificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def payload(self, symbol: str = "VOO", count: int = 1260, granularity: str = "1d") -> bytes:
        start = 1609459200
        timestamps = [start + i * 86400 for i in range(count)]
        return json.dumps({"chart": {"error": None, "result": [{
            "meta": {"symbol": symbol, "dataGranularity": granularity},
            "timestamp": timestamps,
            "indicators": {
                "quote": [{"close": [100.0 + i for i in range(count)]}],
                "adjclose": [{"adjclose": [99.0 + i for i in range(count)]}]
            },
            "events": {"dividends": {}, "splits": {}}
        }]}}).encode("utf-8")

    def record(self, payload: bytes, count: int = 1260, symbol: str = "VOO") -> dict:
        digest = hashlib.sha256(payload).hexdigest()
        document = json.loads(payload.decode("utf-8"))
        timestamps = document["chart"]["result"][0]["timestamp"]
        first_date = datetime.fromtimestamp(timestamps[0], tz=timezone.utc).date().isoformat()
        latest_date = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).date().isoformat()
        return {
            "security_id": f"sec-{symbol}",
            "symbol": symbol,
            "provider_id": "YAHOO_FINANCE_CHART",
            "provider_symbol": symbol,
            "provider_data_granularity": "1d",
            "collection_status": "COLLECTED",
            "payload_sha256": digest,
            "observation_count": count,
            "adjusted_price_observation_count": count,
            "first_observation_date": first_date,
            "latest_observation_date": latest_date,
            "source_lineage": {"raw_path": f"sec-{symbol}.json", "payload_sha256": digest},
        }

    def certify(self, payload: bytes, record: dict, operating_date: str = "2024-06-13") -> dict:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / Path(record["source_lineage"]["raw_path"]).name).write_bytes(payload)
            return certify_record(record, raw_root=root, operating_date=operating_date, policy=self.policy)

    def test_policy_locks_full_population_and_preservation(self):
        self.assertEqual(self.policy["required_record_count"], 3462)
        self.assertTrue(self.policy["preservation"]["all_input_records_preserved"])
        self.assertTrue(self.policy["preservation"]["shorter_history_records_not_deleted"])

    def test_horizon_thresholds_are_exact(self):
        self.assertEqual(self.policy["horizon_minimum_observations"], {"1m": 21, "3m": 63, "1y": 252, "3y": 756, "5y": 1260})

    def test_downstream_authority_remains_false(self):
        forbidden = ["return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
        self.assertTrue(all(self.policy["authority"][key] is False for key in forbidden))

    def test_valid_full_history_is_certified_for_all_horizons(self):
        payload = self.payload()
        result = self.certify(payload, self.record(payload))
        self.assertEqual(result["evidence_state"], "EVIDENCE_CERTIFIED")
        self.assertTrue(all(result["eligible_horizons"].values()))

    def test_short_history_is_preserved_and_horizon_limited(self):
        payload = self.payload(count=252)
        result = self.certify(payload, self.record(payload, count=252), operating_date="2021-09-09")
        self.assertEqual(result["evidence_state"], "HORIZON_LIMITED")
        self.assertTrue(result["eligible_horizons"]["1y"])
        self.assertFalse(result["eligible_horizons"]["3y"])

    def test_hash_mismatch_quarantines_all_horizons(self):
        payload = self.payload()
        record = self.record(payload)
        record["payload_sha256"] = "0" * 64
        result = self.certify(payload, record)
        self.assertEqual(result["evidence_state"], "QUARANTINED")
        self.assertIn("PAYLOAD_HASH_MISMATCH", result["certification_reasons"])
        self.assertFalse(any(result["eligible_horizons"].values()))

    def test_missing_raw_payload_quarantines(self):
        payload = self.payload()
        record = self.record(payload)
        with tempfile.TemporaryDirectory() as temp:
            result = certify_record(record, raw_root=Path(temp), operating_date="2024-06-13", policy=self.policy)
        self.assertIn("RAW_PAYLOAD_MISSING", result["certification_reasons"])

    def test_granularity_mismatch_quarantines(self):
        payload = self.payload(granularity="1mo")
        record = self.record(payload)
        result = self.certify(payload, record)
        self.assertIn("RAW_GRANULARITY_MISMATCH", result["certification_reasons"])

    def test_incomplete_adjusted_prices_quarantine(self):
        document = json.loads(self.payload().decode("utf-8"))
        document["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][-1] = None
        payload = json.dumps(document).encode("utf-8")
        record = self.record(payload)
        result = self.certify(payload, record)
        self.assertIn("INCOMPLETE_ADJUSTED_PRICE_COVERAGE", result["certification_reasons"])

    def test_duplicate_dates_quarantine(self):
        document = json.loads(self.payload().decode("utf-8"))
        document["chart"]["result"][0]["timestamp"][1] = document["chart"]["result"][0]["timestamp"][0]
        payload = json.dumps(document).encode("utf-8")
        record = self.record(payload)
        result = self.certify(payload, record)
        self.assertIn("DUPLICATE_OBSERVATION_DATES", result["certification_reasons"])

    def test_future_observation_quarantines(self):
        payload = self.payload(count=2)
        record = self.record(payload, count=2)
        result = self.certify(payload, record, operating_date="2020-12-31")
        self.assertIn("FUTURE_OBSERVATION_DATE", result["certification_reasons"])

    def test_universe_rejects_duplicate_identity(self):
        payload = self.payload(count=21)
        record = self.record(payload, count=21)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                certify_universe([record] * 3462, raw_root=Path(temp), operating_date="2024-06-13", policy=self.policy)


if __name__ == "__main__":
    unittest.main()
