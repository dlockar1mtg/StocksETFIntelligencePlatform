from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.market.sec_registrant_name_enrichment import SECRegistrantEnrichmentError, extract_required_ciks, normalize_sec_submission

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/sec_registrant_name_enrichment_policy.json").read_text(encoding="utf-8"))


class Phase36B3D1Tests(unittest.TestCase):
    def test_policy_is_fail_closed(self):
        self.assertEqual(POLICY["required_full_population"], 3462)
        self.assertTrue(POLICY["controls"]["fund_name_as_registrant_prohibited"])
        self.assertFalse(POLICY["authority"]["issuer_identity_ledger_rebuild"])

    def test_exact_states(self):
        self.assertEqual(POLICY["states"], ["REGISTRANT_CONFIRMED", "REGISTRANT_UNRESOLVED", "REGISTRANT_CONFLICTED", "REGISTRANT_QUARANTINED", "PILOT_COMPLETE"])

    def test_extracts_unique_confirmed_ciks(self):
        doc = {"records": [
            {"security_id": "A", "resolution_state": "SEC_IDENTITY_CONFIRMED", "sec_cik": "123"},
            {"security_id": "B", "resolution_state": "MATCHED", "sec_cik": "0000000123"},
            {"security_id": "P", "resolution_state": "MATCHED", "sec_cik": "999"},
        ]}
        self.assertEqual(extract_required_ciks(doc, {"P"}), ["0000000123"])

    def test_unconfirmed_identity_excluded(self):
        doc = {"records": [{"security_id": "A", "resolution_state": "UNMATCHED", "sec_cik": "123"}]}
        self.assertEqual(extract_required_ciks(doc, set()), [])

    def test_valid_sec_payload_confirms(self):
        payload = json.dumps({"cik": "123", "name": "Example Trust"}).encode()
        record = normalize_sec_submission(payload, "0000000123", "2026-08-04T00:00:00+00:00")
        self.assertEqual(record["state"], "REGISTRANT_CONFIRMED")
        self.assertEqual(record["registrant_name"], "Example Trust")

    def test_cik_mismatch_conflicts(self):
        payload = json.dumps({"cik": "124", "name": "Example Trust"}).encode()
        self.assertEqual(normalize_sec_submission(payload, "0000000123", "x")["state"], "REGISTRANT_CONFLICTED")

    def test_missing_name_quarantines(self):
        payload = json.dumps({"cik": "123"}).encode()
        self.assertEqual(normalize_sec_submission(payload, "0000000123", "x")["state"], "REGISTRANT_QUARANTINED")

    def test_invalid_json_quarantines(self):
        self.assertEqual(normalize_sec_submission(b"bad", "0000000123", "x")["state"], "REGISTRANT_QUARANTINED")

    def test_hash_is_recorded(self):
        payload = json.dumps({"cik": "123", "name": "Example Trust"}).encode()
        self.assertRegex(normalize_sec_submission(payload, "0000000123", "x")["payload_sha256"], r"^[a-f0-9]{64}$")

    def test_downstream_authorities_false(self):
        for key in ("issuer_batch_planning", "production_taxonomy_classification", "relative_return_calculation", "forecasting", "ranking", "recommendations"):
            self.assertFalse(POLICY["authority"][key])


if __name__ == "__main__":
    unittest.main()
