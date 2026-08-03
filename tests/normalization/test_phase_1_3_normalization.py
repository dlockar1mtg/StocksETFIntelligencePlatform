from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.normalization.point_in_time import (
    NormalizationError,
    load_json,
    reconcile_adjusted_price,
    validate_normalized_record,
    validate_policy,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc)


class Phase13NormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_json(ROOT / "config/normalization/normalization_policy.json")
        security_master = load_json(ROOT / "config/security/security_master.json")
        self.security_ids = {item["security_id"] for item in security_master["securities"]}
        self.record = {
            "security_id": "SEC-US-VOO",
            "ticker": "VOO",
            "domain": "adjusted_price",
            "source_id": "TEST_PROVIDER",
            "source_tier": 3,
            "source_record_id": "record-1",
            "observed_at_utc": "2026-08-03T19:00:00Z",
            "retrieved_at_utc": "2026-08-03T19:05:00Z",
            "content_sha256": "a" * 64,
            "as_of_date": "2026-08-03",
            "effective_at_utc": "2026-08-03T19:00:00Z",
            "available_at_utc": "2026-08-03T19:05:00Z",
            "quality_status": "PASS",
            "normalization_state": "STAGED",
            "imputed_fields": [],
            "critical_conflict": False,
        }

    def validate(self, record: dict) -> None:
        validate_normalized_record(
            record,
            policy=self.policy,
            known_security_ids=self.security_ids,
            now_utc=NOW,
        )

    def test_normalization_policy_is_fail_closed(self) -> None:
        validate_policy(self.policy)
        self.assertFalse(self.policy["certified_analytics_authorized"])

    def test_valid_point_in_time_record_passes(self) -> None:
        self.validate(self.record)

    def test_future_effective_record_is_blocked(self) -> None:
        record = copy.deepcopy(self.record)
        record["effective_at_utc"] = "2026-08-04T00:00:00Z"
        with self.assertRaises(NormalizationError):
            self.validate(record)

    def test_availability_before_effective_is_blocked(self) -> None:
        record = copy.deepcopy(self.record)
        record["available_at_utc"] = "2026-08-03T18:59:00Z"
        with self.assertRaises(NormalizationError):
            self.validate(record)

    def test_ticker_only_identity_is_blocked(self) -> None:
        record = copy.deepcopy(self.record)
        record["security_id"] = "VOO"
        with self.assertRaises(NormalizationError):
            self.validate(record)

    def test_imputed_fields_are_blocked(self) -> None:
        record = copy.deepcopy(self.record)
        record["imputed_fields"] = ["close"]
        with self.assertRaises(NormalizationError):
            self.validate(record)

    def test_critical_conflict_requires_quarantine(self) -> None:
        record = copy.deepcopy(self.record)
        record["critical_conflict"] = True
        with self.assertRaises(NormalizationError):
            self.validate(record)
        record["normalization_state"] = "QUARANTINED"
        record["quality_status"] = "QUARANTINED"
        self.validate(record)

    def test_adjusted_price_reconciliation_is_governed(self) -> None:
        self.assertEqual(
            reconcile_adjusted_price(100.04, 100.00, tolerance_bps=5, corporate_action_evidence_present=True),
            "PASS",
        )
        self.assertEqual(
            reconcile_adjusted_price(100.20, 100.00, tolerance_bps=5, corporate_action_evidence_present=True),
            "QUARANTINED",
        )
        with self.assertRaises(NormalizationError):
            reconcile_adjusted_price(100.00, 100.00, tolerance_bps=5, corporate_action_evidence_present=False)


if __name__ == "__main__":
    unittest.main()
