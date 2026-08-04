from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_registry_acquisition import (
    RegistryAcquisitionError,
    build_acquisition_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/authoritative_etf_taxonomy_registry_acquisition_policy.json").read_text(encoding="utf-8"))


def gaps(count: int = 3462):
    return {"records": [
        {"security_id": f"US-ETF-{i}", "symbol": f"ETF{i}", "classification_status": "UNKNOWN"}
        for i in range(count)
    ]}


class Phase36B3RegistryAcquisitionTests(unittest.TestCase):
    def test_required_population_is_locked(self):
        self.assertEqual(POLICY["required_record_count"], 3462)

    def test_all_new_records_are_preserved_pending(self):
        result = build_acquisition_manifest(gaps(), POLICY)
        self.assertEqual(result["record_count"], 3462)
        self.assertEqual(result["acquisition_state_counts"], {"PENDING": 3462})

    def test_count_drift_fails_closed(self):
        with self.assertRaises(RegistryAcquisitionError):
            build_acquisition_manifest(gaps(2), POLICY)

    def test_duplicate_identity_fails_closed(self):
        document = gaps()
        document["records"][1]["security_id"] = document["records"][0]["security_id"]
        with self.assertRaises(RegistryAcquisitionError):
            build_acquisition_manifest(document, POLICY)

    def test_resume_preserves_terminal_capture(self):
        existing = build_acquisition_manifest(gaps(), POLICY)
        record = existing["records"][0]
        record.update({
            "acquisition_state": "AUTHORITY_CAPTURED",
            "issuer_key": "EXAMPLE_ISSUER",
            "source_tier": "ISSUER_PRODUCT_PAGE",
            "source_id": "EXAMPLE_ISSUER",
            "source_record_id": "ETF0",
            "source_url": "https://example.test/etf0",
            "content_sha256": "1" * 64,
            "captured_at_utc": "2026-08-04T00:00:00+00:00",
            "acquisition_reasons": [],
        })
        result = build_acquisition_manifest(gaps(), POLICY, existing)
        self.assertEqual(result["authority_captured_count"], 1)

    def test_captured_authority_requires_source_url(self):
        existing = build_acquisition_manifest(gaps(), POLICY)
        existing["records"][0].update({
            "acquisition_state": "AUTHORITY_CAPTURED",
            "issuer_key": "EXAMPLE_ISSUER",
            "source_tier": "ISSUER_PRODUCT_PAGE",
            "source_id": "EXAMPLE_ISSUER",
            "source_record_id": "ETF0",
            "content_sha256": "1" * 64,
            "captured_at_utc": "2026-08-04T00:00:00+00:00",
        })
        with self.assertRaises(RegistryAcquisitionError):
            build_acquisition_manifest(gaps(), POLICY, existing)

    def test_invalid_source_tier_fails_closed(self):
        existing = build_acquisition_manifest(gaps(), POLICY)
        existing["records"][0].update({
            "acquisition_state": "AUTHORITY_CAPTURED",
            "issuer_key": "EXAMPLE_ISSUER",
            "source_tier": "SECONDARY_SEARCH",
            "source_id": "EXAMPLE_ISSUER",
            "source_record_id": "ETF0",
            "source_url": "https://example.test/etf0",
            "content_sha256": "1" * 64,
            "captured_at_utc": "2026-08-04T00:00:00+00:00",
        })
        with self.assertRaises(RegistryAcquisitionError):
            build_acquisition_manifest(gaps(), POLICY, existing)

    def test_taxonomy_assignment_is_prohibited(self):
        existing = build_acquisition_manifest(gaps(), POLICY)
        existing["records"][0]["taxonomy_dimensions_assigned"] = True
        with self.assertRaises(RegistryAcquisitionError):
            build_acquisition_manifest(gaps(), POLICY, existing)

    def test_downstream_authorities_remain_false(self):
        for key in (
            "authoritative_source_capture",
            "production_taxonomy_classification",
            "production_taxonomy_certification",
            "relative_return_calculation",
            "risk_analytics",
            "forecasting",
            "ranking",
            "recommendations",
        ):
            self.assertFalse(POLICY["authority"][key])

    def test_manifest_is_not_complete_without_all_authorities(self):
        result = build_acquisition_manifest(gaps(), POLICY)
        self.assertFalse(result["manifest_complete"])
        self.assertEqual(result["next_required_step"], "AUTHORITATIVE_SOURCE_CAPTURE_BY_ISSUER_BATCH")


if __name__ == "__main__":
    unittest.main()
