from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_normalization import (
    AuthoritativeTaxonomyError,
    build_taxonomy_snapshot,
    normalize_taxonomy_record,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase36B2AuthoritativeTaxonomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads((ROOT / "config/market/authoritative_etf_taxonomy_normalization_policy.json").read_text(encoding="utf-8"))
        self.policy["required_record_count"] = 2
        self.evidence = {
            "security_id": "US-ETF-AAA",
            "symbol": "AAA",
            "collection_state": "COLLECTED",
            "provider_symbol": "AAA",
            "provider_payload_sha256": "1" * 64,
            "retrieved_at_utc": "2026-08-04T20:00:00+00:00",
        }
        self.entry = {
            "symbol": "AAA",
            "asset_class": "EQUITY",
            "strategy": "BROAD_MARKET",
            "geography": "UNITED_STATES",
            "market_segment": "LARGE_CAP",
            "income_profile": "DISTRIBUTING",
            "implementation": "PHYSICAL_REPLICATION",
            "specialized_product_type": "NONE",
            "portfolio_treatment": "STANDARD_CANDIDATE",
            "classified_at_utc": "2026-08-04T20:30:00+00:00",
            "source_tier": "ISSUER_PRODUCT_PAGE",
            "source_id": "ISSUER",
            "source_record_id": "AAA",
            "content_sha256": "0123456789abcdef" * 4,
        }

    def test_valid_authoritative_record_is_classified(self) -> None:
        result = normalize_taxonomy_record(self.evidence, self.entry, self.policy)
        self.assertEqual(result["classification_status"], "CLASSIFIED")
        self.assertTrue(result["taxonomy_classification_authorized"])

    def test_missing_registry_entry_remains_unknown(self) -> None:
        result = normalize_taxonomy_record(self.evidence, None, self.policy)
        self.assertEqual(result["classification_status"], "UNKNOWN")
        self.assertIn("AUTHORITATIVE_REGISTRY_ENTRY_MISSING", result["classification_reasons"])

    def test_secondary_evidence_failure_remains_unknown(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["collection_state"] = "NOT_FOUND"
        result = normalize_taxonomy_record(evidence, self.entry, self.policy)
        self.assertEqual(result["classification_status"], "UNKNOWN")

    def test_multiple_authorities_are_conflicted(self) -> None:
        result = normalize_taxonomy_record(self.evidence, [self.entry, copy.deepcopy(self.entry)], self.policy)
        self.assertEqual(result["classification_status"], "CONFLICTED")

    def test_symbol_mismatch_is_conflicted(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["symbol"] = "BBB"
        result = normalize_taxonomy_record(self.evidence, entry, self.policy)
        self.assertEqual(result["classification_status"], "CONFLICTED")

    def test_invalid_or_placeholder_lineage_is_quarantined(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["content_sha256"] = "a" * 64
        result = normalize_taxonomy_record(self.evidence, entry, self.policy)
        self.assertEqual(result["classification_status"], "QUARANTINED")

    def test_missing_dimension_is_quarantined(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["strategy"] = None
        result = normalize_taxonomy_record(self.evidence, entry, self.policy)
        self.assertEqual(result["classification_status"], "QUARANTINED")

    def test_count_drift_fails_closed(self) -> None:
        with self.assertRaises(AuthoritativeTaxonomyError):
            build_taxonomy_snapshot({"records": [self.evidence]}, {"records": {}}, self.policy)

    def test_duplicate_identity_fails_closed(self) -> None:
        with self.assertRaises(AuthoritativeTaxonomyError):
            build_taxonomy_snapshot({"records": [self.evidence, copy.deepcopy(self.evidence)]}, {"records": {}}, self.policy)

    def test_incomplete_population_is_not_certified(self) -> None:
        evidence_b = copy.deepcopy(self.evidence)
        evidence_b["security_id"] = "US-ETF-BBB"
        evidence_b["symbol"] = "BBB"
        result = build_taxonomy_snapshot(
            {"records": [self.evidence, evidence_b]},
            {"records": {self.evidence["security_id"]: self.entry}},
            self.policy,
        )
        self.assertFalse(result["taxonomy_snapshot_certified"])
        self.assertEqual(result["next_required_step"], "AUTHORITATIVE_REGISTRY_REMEDIATION")

    def test_downstream_authorities_remain_false(self) -> None:
        for key in (
            "production_taxonomy_classification",
            "production_taxonomy_certification",
            "benchmark_qualified_universe_publication",
            "relative_return_calculation",
            "risk_analytics",
            "forecasting",
            "ranking",
            "recommendations",
        ):
            self.assertFalse(self.policy["authority"][key])


if __name__ == "__main__":
    unittest.main()
