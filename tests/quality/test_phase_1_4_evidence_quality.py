from __future__ import annotations

import copy
import unittest
from pathlib import Path

from foundation.quality.evidence_quality import (
    EvidenceQualityError,
    load_json,
    validate_evidence,
    validate_quality_policy,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase14EvidenceQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_json(ROOT / "config/quality/evidence_quality_policy.json")
        self.record = {
            "security_id": "SEC-US-VOO",
            "domain": "adjusted_price",
            "provider_id": "TEST-PROVIDER",
            "source_record_id": "record-1",
            "observed_at_utc": "2026-08-03T19:00:00Z",
            "retrieved_at_utc": "2026-08-03T19:05:00Z",
            "as_of_date": "2026-08-03",
            "content_sha256": "a" * 64,
            "quality_status": "PASS",
            "freshness_state": "CURRENT",
            "completeness_ratio": 1.0,
            "confidence_impact": 0.0,
        }

    def test_quality_policy_is_fail_closed(self) -> None:
        validate_quality_policy(self.policy)
        self.assertFalse(self.policy["certified_analytics_authorized"])

    def test_valid_complete_current_evidence_passes(self) -> None:
        validate_evidence(self.record, self.policy)

    def test_missing_required_field_is_blocked(self) -> None:
        record = copy.deepcopy(self.record)
        del record["source_record_id"]
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)

    def test_incomplete_evidence_cannot_pass_or_be_rewarded(self) -> None:
        record = copy.deepcopy(self.record)
        record["completeness_ratio"] = 0.9
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)
        record["quality_status"] = "PROVISIONAL"
        record["confidence_impact"] = 0.0
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)
        record["confidence_impact"] = -0.1
        validate_evidence(record, self.policy)

    def test_unknown_freshness_requires_quarantine(self) -> None:
        record = copy.deepcopy(self.record)
        record["freshness_state"] = "UNKNOWN"
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)
        record["quality_status"] = "QUARANTINED"
        validate_evidence(record, self.policy)

    def test_stale_evidence_cannot_pass(self) -> None:
        record = copy.deepcopy(self.record)
        record["freshness_state"] = "STALE"
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)

    def test_critical_conflict_requires_quarantine(self) -> None:
        record = copy.deepcopy(self.record)
        record["critical_conflict"] = True
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)
        record["quality_status"] = "QUARANTINED"
        validate_evidence(record, self.policy)

    def test_blocked_evidence_cannot_be_promoted(self) -> None:
        record = copy.deepcopy(self.record)
        record["previous_quality_status"] = "BLOCKED"
        with self.assertRaises(EvidenceQualityError):
            validate_evidence(record, self.policy)
        record["quality_status"] = "BLOCKED"
        validate_evidence(record, self.policy)


if __name__ == "__main__":
    unittest.main()
