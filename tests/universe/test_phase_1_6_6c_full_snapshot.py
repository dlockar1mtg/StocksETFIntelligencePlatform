from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from foundation.universe.full_snapshot import FullSnapshotError, build_full_snapshot, reconcile_records, write_full_snapshot


class Phase166CFullSnapshotTests(unittest.TestCase):
    def _candidate(self, symbol: str) -> dict:
        return {
            "security_candidate_id": f"US-ETF-{symbol}",
            "symbol": symbol,
            "security_name": f"{symbol} ETF",
            "primary_exchange": "NYSE_ARCA",
        }

    def _broker(self, symbol: str, status: str = "ELIGIBLE") -> dict:
        return {
            "security_id": f"US-ETF-{symbol}",
            "symbol": symbol,
            "broker_status": status,
            "broker_eligible": status == "ELIGIBLE",
            "robinhood_instrument_id": f"rh-{symbol}" if status == "ELIGIBLE" else None,
            "whole_share_supported": status == "ELIGIBLE",
            "fractional_share_supported": True if status == "ELIGIBLE" else None,
            "fractional_share_evidence_state": "KNOWN" if status == "ELIGIBLE" else "UNKNOWN",
            "recurring_investment_supported": None,
            "recurring_investment_evidence_state": "UNKNOWN",
            "dividend_reinvestment_supported": None,
            "dividend_reinvestment_evidence_state": "UNKNOWN",
            "verified_at_utc": "2026-08-03T23:00:00+00:00",
            "source_id": "ROBINHOOD-PUBLIC-INSTRUMENT-LOOKUP",
            "source_record_id": f"rh-{symbol}",
            "content_sha256": "a" * 64,
            "collection_error": None,
        }

    def _manifest(self) -> dict:
        return {
            "candidate_file_sha256": "a" * 64,
            "quarantine_file_sha256": "b" * 64,
            "availability_file_sha256": "c" * 64,
            "failure_file_sha256": "d" * 64,
        }

    def test_one_to_one_identity_reconciliation(self) -> None:
        records = reconcile_records([self._candidate("VOO")], [self._broker("VOO")])
        self.assertEqual(records[0]["security_id"], "SEC-US-VOO")
        self.assertEqual(records[0]["final_state"], "BROKER_ELIGIBLE")

    def test_missing_broker_identity_fails_closed(self) -> None:
        with self.assertRaises(FullSnapshotError):
            reconcile_records([self._candidate("VOO")], [])

    def test_extra_broker_identity_fails_closed(self) -> None:
        with self.assertRaises(FullSnapshotError):
            reconcile_records([self._candidate("VOO")], [self._broker("VOO"), self._broker("SCHD")])

    def test_security_identity_mismatch_fails_closed(self) -> None:
        broker = self._broker("VOO")
        broker["security_id"] = "WRONG"
        with self.assertRaises(FullSnapshotError):
            reconcile_records([self._candidate("VOO")], [broker])

    def test_eligible_record_requires_robinhood_instrument_id(self) -> None:
        broker = self._broker("VOO")
        broker["robinhood_instrument_id"] = None
        with self.assertRaises(FullSnapshotError):
            reconcile_records([self._candidate("VOO")], [broker])

    def test_restricted_and_sell_only_remain_blocked(self) -> None:
        records = reconcile_records(
            [self._candidate("IPB"), self._candidate("JULP")],
            [self._broker("IPB", "PURCHASE_RESTRICTED"), self._broker("JULP", "SELL_ONLY")],
        )
        self.assertTrue(all(record["final_state"] == "BLOCKED" for record in records))

    def test_taxonomy_and_analytics_remain_pending_or_blocked(self) -> None:
        record = reconcile_records([self._candidate("VOO")], [self._broker("VOO")])[0]
        self.assertEqual(record["taxonomy_status"], "PENDING")
        self.assertEqual(record["analytics_status"], "BLOCKED")

    def test_snapshot_counts_reconcile_and_authority_is_false(self) -> None:
        candidates = [self._candidate("VOO"), self._candidate("SCHD"), self._candidate("QQQM"), self._candidate("IPB")]
        brokers = [self._broker("VOO"), self._broker("SCHD"), self._broker("QQQM"), self._broker("IPB", "PURCHASE_RESTRICTED")]
        manifest = self._manifest()
        snapshot = build_full_snapshot(
            candidates=candidates,
            broker_records=brokers,
            operating_date="2026-08-03",
            exchange_manifest=manifest,
            broker_manifest=manifest,
        )
        self.assertEqual(snapshot["counts"]["total_records"], 4)
        self.assertEqual(snapshot["counts"]["broker_eligible"], 3)
        self.assertEqual(snapshot["counts"]["blocked"], 1)
        self.assertFalse(any(snapshot["attestation"].values()))

    def test_incomplete_lineage_fails_closed(self) -> None:
        manifest = self._manifest()
        del manifest["failure_file_sha256"]
        with self.assertRaises(FullSnapshotError):
            build_full_snapshot(
                candidates=[self._candidate("VOO"), self._candidate("SCHD"), self._candidate("QQQM")],
                broker_records=[self._broker("VOO"), self._broker("SCHD"), self._broker("QQQM")],
                operating_date="2026-08-03",
                exchange_manifest=manifest,
                broker_manifest=manifest,
            )

    def test_snapshot_is_immutable(self) -> None:
        snapshot = {"records": [], "value": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            write_full_snapshot(snapshot, path)
            with self.assertRaises(FullSnapshotError):
                write_full_snapshot({"records": [], "value": 2}, path)


if __name__ == "__main__":
    unittest.main()
