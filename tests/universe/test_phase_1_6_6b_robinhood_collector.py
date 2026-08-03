from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.universe.robinhood_collector import classify_instrument, collect_availability


class Phase166BRobinhoodCollectorTests(unittest.TestCase):
    def _candidate(self, symbol: str = "VOO") -> dict:
        return {"security_candidate_id": f"US-ETF-{symbol}", "symbol": symbol, "candidate_state": "DISCOVERY_CANDIDATE"}

    def test_policy_is_fail_closed_and_resumable(self) -> None:
        policy = json.loads(Path("config/brokers/robinhood_availability_collector_policy.json").read_text())
        self.assertTrue(policy["resume_supported"])
        self.assertTrue(policy["affirmative_buy_evidence_required"])
        self.assertFalse(policy["unknown_or_failed_lookup_is_eligible"])
        self.assertFalse(policy["automatic_execution_authorized"])

    def test_affirmative_tradable_result_is_eligible(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": [{"id": "abc", "symbol": "VOO", "tradeable": True, "tradability": "tradable", "fractional_tradability": "tradable", "recurring_investment_eligible": True, "drip_eligible": True}]},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertEqual(record["broker_status"], "ELIGIBLE")
        self.assertTrue(record["broker_eligible"])
        self.assertTrue(record["whole_share_supported"])

    def test_successful_record_has_explicit_null_collection_error(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": [{"id": "abc", "symbol": "VOO", "tradeable": True, "tradability": "tradable"}]},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertIn("collection_error", record)
        self.assertIsNone(record["collection_error"])

    def test_missing_capability_evidence_remains_unknown(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": [{"id": "abc", "symbol": "VOO", "tradeable": True, "tradability": "tradable"}]},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertIsNone(record["fractional_share_supported"])
        self.assertIsNone(record["recurring_investment_supported"])
        self.assertIsNone(record["dividend_reinvestment_supported"])
        self.assertEqual(record["recurring_investment_evidence_state"], "UNKNOWN")

    def test_position_closing_only_is_sell_only(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": [{"id": "abc", "symbol": "VOO", "tradeable": True, "tradability": "position_closing_only"}]},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertEqual(record["broker_status"], "SELL_ONLY")
        self.assertFalse(record["broker_eligible"])

    def test_not_found_is_not_eligible(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": []},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertEqual(record["broker_status"], "NOT_FOUND")
        self.assertFalse(record["broker_eligible"])

    def test_duplicate_exact_matches_are_conflicted(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": [{"symbol": "VOO"}, {"symbol": "VOO"}]},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertEqual(record["broker_status"], "CONFLICTED")

    def test_capabilities_are_independent(self) -> None:
        record = classify_instrument(
            self._candidate(),
            {"results": [{"id": "abc", "symbol": "VOO", "tradeable": True, "tradability": "tradable", "fractional_tradability": "unavailable", "recurring_investment_eligible": False, "drip_eligible": False}]},
            retrieved_at_utc="2026-08-03T21:00:00+00:00",
            source_url="https://example.test",
            raw_sha256="a" * 64,
        )
        self.assertTrue(record["broker_eligible"])
        self.assertFalse(record["fractional_share_supported"])
        self.assertFalse(record["recurring_investment_supported"])

    def test_collection_is_resumable_and_writes_hashes(self) -> None:
        def fake_fetch(symbol: str, **_: object):
            raw = json.dumps({"results": [{"id": symbol.lower(), "symbol": symbol, "tradeable": True, "tradability": "tradable"}]}).encode()
            return json.loads(raw), raw, f"https://example.test/{symbol}"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = collect_availability([self._candidate("VOO")], output_root=root, operating_date="2026-08-03", url_template="x", minimum_delay_seconds=0, fetcher=fake_fetch)
            second = collect_availability([self._candidate("VOO"), self._candidate("SCHD")], output_root=root, operating_date="2026-08-03", url_template="x", minimum_delay_seconds=0, fetcher=fake_fetch)
            self.assertEqual(first["completed_count"], 1)
            self.assertEqual(second["completed_count"], 2)
            self.assertEqual(len(second["availability_file_sha256"]), 64)

    def test_failed_lookup_fails_closed(self) -> None:
        def broken_fetch(symbol: str, **_: object):
            raise RuntimeError(symbol)

        with tempfile.TemporaryDirectory() as tmp:
            manifest = collect_availability([self._candidate()], output_root=Path(tmp), operating_date="2026-08-03", url_template="x", minimum_delay_seconds=0, fetcher=broken_fetch)
            self.assertEqual(manifest["broker_eligible_count"], 0)
            self.assertEqual(manifest["failed_lookup_count"], 1)

    def test_retry_failed_replaces_error_without_duplicate_record(self) -> None:
        calls = {"count": 0}

        def flaky_fetch(symbol: str, **_: object):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError(symbol)
            raw = json.dumps({"results": [{"id": "abc", "symbol": symbol, "tradeable": True, "tradability": "tradable"}]}).encode()
            return json.loads(raw), raw, f"https://example.test/{symbol}"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = collect_availability([self._candidate()], output_root=root, operating_date="2026-08-03", url_template="x", minimum_delay_seconds=0, fetcher=flaky_fetch)
            second = collect_availability([self._candidate()], output_root=root, operating_date="2026-08-03", url_template="x", minimum_delay_seconds=0, fetcher=flaky_fetch, retry_failed=True)
            lines = (root / "staged" / "2026-08-03" / "robinhood_availability_records.jsonl").read_text().splitlines()
            self.assertEqual(first["failed_lookup_count"], 1)
            self.assertEqual(second["failed_lookup_count"], 0)
            self.assertEqual(second["broker_eligible_count"], 1)
            self.assertEqual(len(lines), 1)

    def test_collector_grants_no_analytics_or_execution_authority(self) -> None:
        policy = json.loads(Path("config/brokers/robinhood_availability_collector_policy.json").read_text())
        self.assertFalse(policy["certified_analytics_authorized"])
        self.assertFalse(policy["certified_recommendations_authorized"])
        self.assertFalse(policy["direct_uip_database_writes_authorized"])


if __name__ == "__main__":
    unittest.main()
