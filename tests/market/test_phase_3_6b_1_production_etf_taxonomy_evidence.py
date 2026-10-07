from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from foundation.market.production_etf_taxonomy_evidence import TaxonomyEvidenceError, build_url, normalize_payload, provider_error_record

ROOT = Path(__file__).resolve().parents[2]


class Phase36B1TaxonomyEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads((ROOT / "config/market/production_etf_taxonomy_evidence_policy.json").read_text(encoding="utf-8"))
        self.payload = json.dumps({"quotes": [{"symbol": "VOO", "quoteType": "ETF", "shortname": "Vanguard S&P 500 ETF", "longname": "Vanguard S&P 500 ETF", "exchange": "PCX"}]}).encode()

    def test_required_population_is_locked(self) -> None:
        self.assertEqual(self.policy["required_record_count"], 3462)

    def test_seeds_are_exact(self) -> None:
        self.assertEqual(self.policy["required_seed_symbols"], ["VOO", "SCHD", "QQQM"])

    def test_url_uses_governed_endpoint(self) -> None:
        self.assertIn("q=VOO", build_url("VOO", self.policy))

    def test_invalid_symbol_fails_closed(self) -> None:
        with self.assertRaises(TaxonomyEvidenceError):
            build_url("VOO/../../", self.policy)

    def test_exact_provider_match_is_collected(self) -> None:
        record = normalize_payload("US-ETF-VOO", "VOO", self.payload, "2026-08-04T20:00:00+00:00")
        self.assertEqual(record["collection_state"], "COLLECTED")
        self.assertEqual(record["provider_payload_sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertFalse(record["taxonomy_classification_authorized"])

    def test_missing_quote_is_preserved(self) -> None:
        record = normalize_payload("US-ETF-VOO", "VOO", b'{"quotes": []}')
        self.assertEqual(record["collection_state"], "NOT_FOUND")

    def test_symbol_mismatch_is_preserved(self) -> None:
        record = normalize_payload("US-ETF-VOO", "VOO", b'{"quotes": [{"symbol": "SPY"}]}')
        self.assertEqual(record["collection_state"], "SYMBOL_MISMATCH")

    def test_malformed_payload_fails_closed(self) -> None:
        with self.assertRaises(TaxonomyEvidenceError):
            normalize_payload("US-ETF-VOO", "VOO", b"not-json")

    def test_provider_error_is_preserved(self) -> None:
        record = provider_error_record("US-ETF-VOO", "VOO", RuntimeError("boom"))
        self.assertEqual(record["collection_state"], "PROVIDER_ERROR")
        self.assertFalse(record["taxonomy_classification_authorized"])

    def test_downstream_authorities_remain_false(self) -> None:
        for key in ("production_taxonomy_classification", "benchmark_qualified_universe_publication", "relative_return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations"):
            self.assertFalse(self.policy["authority"][key])


if __name__ == "__main__":
    unittest.main()
