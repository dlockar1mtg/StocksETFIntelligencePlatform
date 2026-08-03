from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.universe.broker_eligibility import (
    BrokerEligibilityError,
    build_broker_snapshot,
    evaluate_broker_record,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/brokers/robinhood_eligibility_policy.json").read_text(encoding="utf-8"))
AS_OF = datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc)


def valid_record() -> dict:
    return {
        "security_id": "SEC-US-VOO",
        "broker_id": "ROBINHOOD-US",
        "broker_status": "ELIGIBLE",
        "whole_share_supported": True,
        "fractional_share_supported": True,
        "recurring_investment_supported": True,
        "dividend_reinvestment_supported": True,
        "verified_at_utc": "2026-08-03T19:00:00+00:00",
        "effective_at_utc": "2026-08-03T18:00:00+00:00",
        "available_at_utc": "2026-08-03T19:00:00+00:00",
        "verification_method": "BROKER_SECURITY_PAGE",
        "verification_confidence": 0.95,
        "source_id": "ROBINHOOD-OFFICIAL",
        "source_record_id": "voo-20260803",
        "content_sha256": "a" * 64,
    }


class Phase163RobinhoodEligibilityTests(unittest.TestCase):
    def test_policy_is_time_dependent_and_fail_closed(self):
        self.assertTrue(POLICY["eligibility_is_time_dependent"])
        self.assertTrue(POLICY["fail_closed"])
        self.assertFalse(POLICY["listing_does_not_imply_broker_eligibility"] is False)

    def test_valid_record_is_broker_eligible(self):
        self.assertEqual(evaluate_broker_record(valid_record(), POLICY, AS_OF), "BROKER_ELIGIBLE")

    def test_unknown_and_conflicted_statuses_are_quarantined(self):
        for status in ("UNKNOWN", "CONFLICTED"):
            record = valid_record()
            record["broker_status"] = status
            self.assertEqual(evaluate_broker_record(record, POLICY, AS_OF), "QUARANTINED")

    def test_restricted_or_sell_only_status_is_blocked(self):
        for status in ("PURCHASE_RESTRICTED", "SELL_ONLY", "TEMPORARILY_UNAVAILABLE", "DELISTED"):
            record = valid_record()
            record["broker_status"] = status
            self.assertEqual(evaluate_broker_record(record, POLICY, AS_OF), "BLOCKED")

    def test_capabilities_are_independent(self):
        record = valid_record()
        record["fractional_share_supported"] = False
        record["recurring_investment_supported"] = False
        record["dividend_reinvestment_supported"] = False
        self.assertEqual(evaluate_broker_record(record, POLICY, AS_OF), "BROKER_ELIGIBLE")

    def test_whole_share_support_is_required(self):
        record = valid_record()
        record["whole_share_supported"] = False
        self.assertEqual(evaluate_broker_record(record, POLICY, AS_OF), "BLOCKED")

    def test_future_and_stale_evidence_fail_closed(self):
        future = valid_record()
        future["available_at_utc"] = "2026-08-04T00:00:00+00:00"
        with self.assertRaises(BrokerEligibilityError):
            evaluate_broker_record(future, POLICY, AS_OF)
        stale = valid_record()
        stale["verified_at_utc"] = "2026-07-01T00:00:00+00:00"
        self.assertEqual(evaluate_broker_record(stale, POLICY, AS_OF), "STALE")

    def test_missing_low_confidence_and_duplicate_records_are_blocked(self):
        missing = valid_record()
        del missing["source_record_id"]
        with self.assertRaises(BrokerEligibilityError):
            evaluate_broker_record(missing, POLICY, AS_OF)
        low = valid_record()
        low["verification_confidence"] = 0.5
        self.assertEqual(evaluate_broker_record(low, POLICY, AS_OF), "BLOCKED")
        with self.assertRaises(BrokerEligibilityError):
            build_broker_snapshot([valid_record(), copy.deepcopy(valid_record())], POLICY, AS_OF)

    def test_contract_is_registered(self):
        registry = json.loads((ROOT / "config/contracts/contract_registry.json").read_text(encoding="utf-8"))
        ids = {item["contract_id"] for item in registry["contracts"]}
        self.assertIn("native.broker_eligibility_record", ids)


if __name__ == "__main__":
    unittest.main()
