from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.universe.exchange_collector import (
    ExchangeCollectorError,
    SourcePayload,
    parse_symbol_directory,
    reconcile_candidates,
    write_collection,
)


class Phase166AExchangeCollectorTests(unittest.TestCase):
    def _payload(self, source_id: str, text: str) -> SourcePayload:
        data = text.encode("utf-8")
        return SourcePayload(
            source_id=source_id,
            url="https://example.test/source.txt",
            retrieved_at_utc="2026-08-03T20:00:00+00:00",
            content_sha256="a" * 64,
            byte_count=len(data),
            payload=data,
        )

    def test_policy_is_fail_closed_and_broker_independent(self) -> None:
        policy = json.loads(Path("config/universe/us_etf_exchange_collector_policy.json").read_text())
        self.assertTrue(policy["raw_payloads_must_remain_outside_git"])
        self.assertTrue(policy["content_sha256_required"])
        self.assertFalse(policy["candidate_is_certified_discovery"])
        self.assertFalse(policy["candidate_implies_robinhood_eligibility"])
        self.assertFalse(policy["automatic_execution_authorized"])

    def test_runner_invokes_collector_as_repository_module(self) -> None:
        runner = Path("run_us_etf_exchange_collection.ps1").read_text(encoding="utf-8")
        self.assertIn('python -m $CollectorModule', runner)
        self.assertIn('scripts.collect_us_etf_exchange_universe', runner)
        self.assertNotIn('python .\\scripts\\collect_us_etf_exchange_universe.py', runner)

    def test_nasdaq_etf_candidate_is_parsed(self) -> None:
        payload = self._payload(
            "NASDAQ-TRADER-NASDAQLISTED",
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nABC|ABC Index Fund|G|N|N|100|Y|N\nFile Creation Time: 202608032000|\n",
        )
        candidates, quarantine = parse_symbol_directory(payload)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["symbol"], "ABC")
        self.assertEqual(candidates[0]["primary_exchange"], "NASDAQ")
        self.assertFalse(candidates[0]["robinhood_eligible"])
        self.assertEqual(quarantine, [])

    def test_otherlisted_etf_candidate_is_parsed(self) -> None:
        payload = self._payload(
            "NASDAQ-TRADER-OTHERLISTED",
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\nXYZ|XYZ Market ETF|P|XYZ|Y|100|N|XYZ\nFile Creation Time: 202608032000|\n",
        )
        candidates, _ = parse_symbol_directory(payload)
        self.assertEqual(candidates[0]["primary_exchange"], "NYSE_ARCA")

    def test_non_etf_rows_are_excluded(self) -> None:
        payload = self._payload(
            "NASDAQ-TRADER-NASDAQLISTED",
            "Symbol|Security Name|Test Issue|ETF\nABC|ABC Common Stock|N|N\n",
        )
        candidates, quarantine = parse_symbol_directory(payload)
        self.assertEqual(candidates, [])
        self.assertEqual(quarantine, [])

    def test_test_issue_and_missing_identity_are_quarantined(self) -> None:
        payload = self._payload(
            "NASDAQ-TRADER-NASDAQLISTED",
            "Symbol|Security Name|Test Issue|ETF\nTST|Test ETF|Y|Y\n|Missing Symbol ETF|N|Y\n",
        )
        candidates, quarantine = parse_symbol_directory(payload)
        self.assertEqual(candidates, [])
        self.assertEqual(len(quarantine), 2)

    def test_etn_and_closed_end_patterns_are_quarantined(self) -> None:
        payload = self._payload(
            "NASDAQ-TRADER-NASDAQLISTED",
            "Symbol|Security Name|Test Issue|ETF\nNOTE|Example ETN|N|Y\nCEF|Example Closed-End Fund|N|Y\n",
        )
        candidates, quarantine = parse_symbol_directory(payload)
        self.assertEqual(candidates, [])
        self.assertEqual(len(quarantine), 2)

    def test_duplicate_identical_candidates_are_reconciled(self) -> None:
        base = {
            "symbol": "ABC",
            "security_name": "ABC ETF",
            "primary_exchange": "NASDAQ",
            "source_id": "A",
            "source_row_number": 2,
        }
        second = dict(base)
        second["source_id"] = "B"
        accepted, quarantine = reconcile_candidates([base, second])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["source_record_count"], 2)
        self.assertEqual(quarantine, [])

    def test_conflicting_identity_is_quarantined(self) -> None:
        first = {"symbol": "ABC", "security_name": "ABC ETF", "primary_exchange": "NASDAQ", "source_id": "A", "source_row_number": 2}
        second = {"symbol": "ABC", "security_name": "Different ETF", "primary_exchange": "NYSE", "source_id": "B", "source_row_number": 3}
        accepted, quarantine = reconcile_candidates([first, second])
        self.assertEqual(accepted, [])
        self.assertEqual(quarantine[0]["quarantine_reason"], "CONFLICTING_EXCHANGE_IDENTITY")

    def test_collection_outputs_manifest_and_hashes(self) -> None:
        payload = self._payload("NASDAQ-TRADER-NASDAQLISTED", "Symbol|Security Name|Test Issue|ETF\nABC|ABC ETF|N|Y\n")
        candidates, quarantine = parse_symbol_directory(payload)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_collection(
                source_payloads=[payload],
                candidates=candidates,
                quarantined=quarantine,
                output_root=Path(tmp),
                operating_date="2026-08-03",
            )
            self.assertEqual(manifest["candidate_count"], 1)
            self.assertEqual(len(manifest["candidate_file_sha256"]), 64)
            self.assertFalse(manifest["candidate_implies_robinhood_eligibility"])

    def test_raw_payload_collision_fails_closed(self) -> None:
        payload = self._payload("NASDAQ-TRADER-NASDAQLISTED", "Symbol|Security Name|Test Issue|ETF\nABC|ABC ETF|N|Y\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw" / "2026-08-03"
            raw.mkdir(parents=True)
            (raw / "nasdaq_trader_nasdaqlisted.txt").write_text("different", encoding="utf-8")
            with self.assertRaises(ExchangeCollectorError):
                write_collection(
                    source_payloads=[payload],
                    candidates=[],
                    quarantined=[],
                    output_root=root,
                    operating_date="2026-08-03",
                )


if __name__ == "__main__":
    unittest.main()
