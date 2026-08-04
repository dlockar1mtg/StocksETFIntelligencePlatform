import json
import unittest
from pathlib import Path

from foundation.market.pilot_taxonomy_normalization import normalize_pilot_record, summarize

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/pilot_taxonomy_normalization_policy.json").read_text())
REGISTRY = json.loads((ROOT / "config/market/pilot_taxonomy_registry.json").read_text())["records"]


class Phase36B3BPilotTaxonomyTests(unittest.TestCase):
    def test_required_identities_are_exact(self):
        self.assertEqual(set(POLICY["required_security_ids"]), {"SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"})

    def test_registry_covers_all_pilot_identities(self):
        self.assertEqual(set(REGISTRY), set(POLICY["required_security_ids"]))

    def test_all_required_dimensions_exist(self):
        for entry in REGISTRY.values():
            for field in POLICY["required_dimensions"]:
                self.assertTrue(entry[field])

    def test_valid_captured_record_classifies(self):
        manifest = {"security_id": "SEC-US-VOO", "symbol": "VOO", "acquisition_state": "AUTHORITY_CAPTURED", "source_content_sha256": "a" * 64}
        record = normalize_pilot_record(manifest, REGISTRY["SEC-US-VOO"], POLICY)
        self.assertEqual(record["classification_status"], "CLASSIFIED")
        self.assertTrue(record["taxonomy_classification_authorized"])
        self.assertFalse(record["production_taxonomy_authority"])

    def test_missing_hash_quarantines_captured_record(self):
        manifest = {"security_id": "SEC-US-VOO", "symbol": "VOO", "acquisition_state": "AUTHORITY_CAPTURED", "source_content_sha256": None}
        record = normalize_pilot_record(manifest, REGISTRY["SEC-US-VOO"], POLICY)
        self.assertEqual(record["classification_status"], "QUARANTINED")

    def test_schd_sec_content_classifies(self):
        manifest = {"security_id": "SEC-US-SCHD", "symbol": "SCHD", "acquisition_state": "UNRESOLVED", "source_content_sha256": None}
        content = b"Schwab U.S. Dividend Equity ETF SCHD Dow Jones U.S. Dividend 100"
        record = normalize_pilot_record(manifest, REGISTRY["SEC-US-SCHD"], POLICY, content)
        self.assertEqual(record["classification_status"], "CLASSIFIED")

    def test_missing_content_terms_quarantines(self):
        manifest = {"security_id": "SEC-US-SCHD", "symbol": "SCHD", "acquisition_state": "UNRESOLVED", "source_content_sha256": None}
        record = normalize_pilot_record(manifest, REGISTRY["SEC-US-SCHD"], POLICY, b"unrelated")
        self.assertEqual(record["classification_status"], "QUARANTINED")

    def test_incomplete_pilot_requires_remediation(self):
        summary = summarize([{"classification_status": "CLASSIFIED"}, {"classification_status": "UNRESOLVED"}], POLICY)
        self.assertFalse(summary["pilot_taxonomy_complete"])
        self.assertEqual(summary["next_required_step"], "PILOT_SOURCE_REMEDIATION")

    def test_complete_pilot_advances_to_batch_expansion(self):
        summary = summarize([{"classification_status": "CLASSIFIED"}] * 3, POLICY)
        self.assertTrue(summary["pilot_taxonomy_complete"])
        self.assertEqual(summary["next_required_step"], "ISSUER_BATCH_EXPANSION")

    def test_downstream_authorities_remain_false(self):
        for key in ("production_taxonomy_classification", "relative_return_calculation", "risk_analytics", "forecasting", "ranking"):
            self.assertFalse(POLICY["authority"][key])


if __name__ == "__main__":
    unittest.main()
