import json
import unittest
from pathlib import Path

from foundation.market.issuer_source_capture_pilot import (
    IssuerSourceCaptureError,
    capture_record,
    failure_record,
    validate_registry_entry,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/issuer_source_capture_pilot_policy.json").read_text())
REGISTRY = json.loads((ROOT / "config/market/issuer_source_capture_pilot_registry.json").read_text())["records"]


class Phase36B3AIssuerCaptureTests(unittest.TestCase):
    def test_pilot_symbols_are_exact(self):
        self.assertEqual(POLICY["pilot_symbols"], ["VOO", "SCHD", "QQQM"])

    def test_required_count_is_three(self):
        self.assertEqual(POLICY["required_record_count"], 3)

    def test_registry_has_three_stable_identities(self):
        self.assertEqual(set(REGISTRY), {"US-ETF-VOO", "US-ETF-SCHD", "US-ETF-QQQM"})

    def test_official_https_domains_validate(self):
        for security_id, entry in REGISTRY.items():
            validate_registry_entry(security_id, entry, POLICY)

    def test_unofficial_domain_fails_closed(self):
        entry = dict(REGISTRY["US-ETF-VOO"])
        entry["source_url"] = "https://example.com/voo"
        with self.assertRaises(IssuerSourceCaptureError):
            validate_registry_entry("US-ETF-VOO", entry, POLICY)

    def test_valid_content_is_captured(self):
        entry = REGISTRY["US-ETF-VOO"]
        record = capture_record("US-ETF-VOO", entry, POLICY, b"Vanguard VOO official fund page")
        self.assertEqual(record["acquisition_state"], "AUTHORITY_CAPTURED")
        self.assertRegex(record["source_content_sha256"], r"^[a-f0-9]{64}$")

    def test_missing_symbol_is_quarantined(self):
        entry = REGISTRY["US-ETF-VOO"]
        record = capture_record("US-ETF-VOO", entry, POLICY, b"Vanguard official fund page")
        self.assertEqual(record["acquisition_state"], "QUARANTINED")

    def test_failure_is_preserved(self):
        record = failure_record("US-ETF-VOO", REGISTRY["US-ETF-VOO"], RuntimeError("blocked"))
        self.assertEqual(record["acquisition_state"], "UNRESOLVED")

    def test_taxonomy_authority_remains_false(self):
        entry = REGISTRY["US-ETF-SCHD"]
        record = capture_record("US-ETF-SCHD", entry, POLICY, b"Schwab SCHD official page")
        self.assertFalse(record["taxonomy_classification_authorized"])
        self.assertFalse(record["taxonomy_dimensions_assigned"])

    def test_downstream_authorities_remain_false(self):
        for key in ("production_taxonomy_classification", "relative_return_calculation", "risk_analytics", "forecasting", "ranking"):
            self.assertFalse(POLICY["authority"][key])


if __name__ == "__main__":
    unittest.main()
