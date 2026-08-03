from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.universe.discovery import (
    ETFDiscoveryError,
    build_snapshot,
    validate_discovery_policy,
    validate_discovery_record,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "universe" / "etf_discovery_policy.json"
REGISTRY_PATH = ROOT / "config" / "contracts" / "contract_registry.json"
SCHEMA_PATH = ROOT / "contracts" / "native" / "etf_discovery_record.schema.json"
NOW = datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc)


class Phase162ETFDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.record = {
            "security_id": "SEC-US-TESTETF",
            "ticker": "TEST",
            "legal_name": "Test ETF",
            "instrument_type": "ETF",
            "primary_exchange": "NYSE_ARCA",
            "issuer_name": "Test Sponsor",
            "listing_status": "ACTIVE",
            "effective_at_utc": "2026-08-01T14:00:00Z",
            "available_at_utc": "2026-08-01T15:00:00Z",
            "source_ids": ["SEC-N1A-TEST", "NYSE-LISTING-TEST"],
            "content_sha256": "a" * 64,
            "prior_tickers": [],
            "quarantine_reasons": [],
        }

    def test_discovery_policy_is_fail_closed(self) -> None:
        validate_discovery_policy(self.policy)
        self.assertFalse(self.policy["broker_eligibility_inferred_from_listing"])
        self.assertFalse(self.policy["analytics_eligibility_inferred_from_listing"])

    def test_discovery_contract_is_registered(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        contracts = {item["contract_id"]: item for item in registry["contracts"]}
        self.assertIn("native.etf_discovery_record", contracts)
        self.assertTrue(SCHEMA_PATH.is_file())

    def test_valid_active_etf_is_discovered_not_broker_eligible(self) -> None:
        result = validate_discovery_record(self.record, self.policy, as_of_utc=NOW)
        self.assertEqual(result["discovery_state"], "DISCOVERED")
        self.assertTrue(result["active_listing"])
        self.assertFalse(result["broker_eligible"])
        self.assertFalse(result["analytics_eligible"])

    def test_non_etf_instruments_are_rejected(self) -> None:
        broken = copy.deepcopy(self.record)
        broken["instrument_type"] = "ETN"
        with self.assertRaises(ETFDiscoveryError):
            validate_discovery_record(broken, self.policy, as_of_utc=NOW)

    def test_two_authorities_and_sec_or_exchange_evidence_are_required(self) -> None:
        broken = copy.deepcopy(self.record)
        broken["source_ids"] = ["ISSUER-TEST"]
        with self.assertRaises(ETFDiscoveryError):
            validate_discovery_record(broken, self.policy, as_of_utc=NOW)
        broken["source_ids"] = ["ISSUER-TEST", "VENDOR-TEST"]
        with self.assertRaises(ETFDiscoveryError):
            validate_discovery_record(broken, self.policy, as_of_utc=NOW)

    def test_unknown_and_future_listing_records_are_blocked(self) -> None:
        unknown = copy.deepcopy(self.record)
        unknown["listing_status"] = "UNKNOWN"
        with self.assertRaises(ETFDiscoveryError):
            validate_discovery_record(unknown, self.policy, as_of_utc=NOW)
        future = copy.deepcopy(self.record)
        future["available_at_utc"] = "2026-08-04T15:00:00Z"
        with self.assertRaises(ETFDiscoveryError):
            validate_discovery_record(future, self.policy, as_of_utc=NOW)

    def test_conflicted_or_inactive_records_are_quarantined(self) -> None:
        conflicted = copy.deepcopy(self.record)
        conflicted["quarantine_reasons"] = ["INSTRUMENT_TYPE_CONFLICT"]
        result = validate_discovery_record(conflicted, self.policy, as_of_utc=NOW)
        self.assertEqual(result["discovery_state"], "QUARANTINED")
        inactive = copy.deepcopy(self.record)
        inactive["listing_status"] = "LIQUIDATING"
        result = validate_discovery_record(inactive, self.policy, as_of_utc=NOW)
        self.assertFalse(result["active_listing"])

    def test_snapshot_is_immutable_and_rejects_duplicate_identity(self) -> None:
        snapshot = build_snapshot([self.record], self.policy, snapshot_id="us-etf-20260803")
        self.assertTrue(snapshot["immutable"])
        self.assertEqual(snapshot["active_security_ids"], ["SEC-US-TESTETF"])
        with self.assertRaises(ETFDiscoveryError):
            build_snapshot([self.record, copy.deepcopy(self.record)], self.policy, snapshot_id="duplicate")


if __name__ == "__main__":
    unittest.main()
