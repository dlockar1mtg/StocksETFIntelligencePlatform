from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.universe.taxonomy import ETFTaxonomyError, validate_taxonomy_record, validate_taxonomy_snapshot

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 3, 21, 0, tzinfo=timezone.utc)


class Phase164ETFTaxonomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads((ROOT / "config/universe/etf_taxonomy_policy.json").read_text(encoding="utf-8"))
        self.record = {
            "security_id": "SEC-US-VOO",
            "asset_class": "EQUITY",
            "strategy": "BROAD_MARKET",
            "geography": "UNITED_STATES",
            "market_segment": "LARGE_CAP",
            "income_profile": "DISTRIBUTING",
            "implementation": "PHYSICAL_REPLICATION",
            "specialized_product_type": "NONE",
            "portfolio_treatment": "STANDARD_CANDIDATE",
            "classification_status": "CLASSIFIED",
            "classified_at_utc": "2026-08-03T20:00:00+00:00",
            "source_id": "ISSUER-PROSPECTUS",
            "source_record_id": "VOO-2026",
            "content_sha256": "a" * 64,
        }

    def test_policy_is_complete_and_fail_closed(self) -> None:
        self.assertTrue(self.policy["fail_closed"])
        self.assertFalse(self.policy["classification_requirements"]["unknown_dimension_allowed"])
        self.assertTrue(self.policy["classification_requirements"]["conflicting_classification_quarantined"])

    def test_contract_is_registered(self) -> None:
        registry = json.loads((ROOT / "config/contracts/contract_registry.json").read_text(encoding="utf-8"))
        ids = {item["contract_id"] for item in registry["contracts"]}
        self.assertIn("native.etf_taxonomy_record", ids)

    def test_standard_etf_can_be_standard_candidate(self) -> None:
        self.assertEqual(validate_taxonomy_record(self.record, self.policy, NOW), "STANDARD_CANDIDATE")

    def test_specialized_products_require_nonstandard_treatment(self) -> None:
        broken = copy.deepcopy(self.record)
        broken["strategy"] = "LEVERAGED"
        broken["specialized_product_type"] = "LEVERAGED"
        with self.assertRaises(ETFTaxonomyError):
            validate_taxonomy_record(broken, self.policy, NOW)
        broken["portfolio_treatment"] = "SPECIALIZED_REVIEW_REQUIRED"
        self.assertEqual(validate_taxonomy_record(broken, self.policy, NOW), "SPECIALIZED_REVIEW_REQUIRED")

    def test_unknown_dimensions_fail_closed(self) -> None:
        broken = copy.deepcopy(self.record)
        broken["asset_class"] = "UNKNOWN"
        with self.assertRaises(ETFTaxonomyError):
            validate_taxonomy_record(broken, self.policy, NOW)

    def test_conflicted_or_unknown_classification_is_quarantined(self) -> None:
        for status in ("CONFLICTED", "UNKNOWN", "QUARANTINED"):
            record = copy.deepcopy(self.record)
            record["classification_status"] = status
            self.assertEqual(validate_taxonomy_record(record, self.policy, NOW), "QUARANTINED")

    def test_future_or_invalid_evidence_is_blocked(self) -> None:
        future = copy.deepcopy(self.record)
        future["classified_at_utc"] = "2026-08-04T00:00:00+00:00"
        with self.assertRaises(ETFTaxonomyError):
            validate_taxonomy_record(future, self.policy, NOW)
        future = copy.deepcopy(self.record)
        future["content_sha256"] = "bad"
        with self.assertRaises(ETFTaxonomyError):
            validate_taxonomy_record(future, self.policy, NOW)

    def test_duplicate_security_classification_is_blocked(self) -> None:
        with self.assertRaises(ETFTaxonomyError):
            validate_taxonomy_snapshot([self.record, copy.deepcopy(self.record)], self.policy, NOW)

    def test_taxonomy_grants_no_downstream_authority(self) -> None:
        self.assertTrue(self.policy["taxonomy_does_not_imply_analytics_eligibility"])
        self.assertTrue(self.policy["taxonomy_does_not_imply_recommendation_eligibility"])
        self.assertTrue(self.policy["taxonomy_does_not_imply_portfolio_suitability"])
        self.assertFalse(self.policy["automatic_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
