from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from foundation.market.issuer_identity_ledger_rebuild import IssuerLedgerRebuildError, build_issuer_identity_ledger

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/issuer_identity_ledger_rebuild_policy.json").read_text(encoding="utf-8"))


class Phase36B3D2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = copy.deepcopy(POLICY)
        self.policy["required_full_population"] = 2
        self.plan = {"records": [
            {"security_id": "SEC-US-AAA", "symbol": "AAA"},
            {"security_id": "SEC-US-VOO", "symbol": "VOO"},
        ]}
        self.sec = {"records": [
            {"security_id": "SEC-US-AAA", "resolution_state": "SEC_IDENTITY_CONFIRMED", "sec_cik": "1234"}
        ]}
        self.registry = {"records": [
            {"cik": "0000001234", "state": "REGISTRANT_CONFIRMED", "registrant_name": "Example Trust", "payload_sha256": "a" * 64, "retrieved_at_utc": "2026-08-04T00:00:00Z"}
        ]}
        self.pilot = {"records": [
            {"security_id": "SEC-US-VOO", "classification_status": "CLASSIFIED", "issuer_key": "VANGUARD", "source_tier": "ISSUER_PRODUCT_PAGE", "source_record_id": "VOO", "content_sha256": "b" * 64}
        ]}

    def build(self):
        return build_issuer_identity_ledger(self.plan, self.sec, self.registry, self.pilot, self.policy)

    def test_confirmed_registry_join_creates_issuer(self):
        record = self.build()["records"][0]
        self.assertEqual(record["issuer_identity_state"], "ISSUER_CONFIRMED")
        self.assertEqual(record["issuer_key"], "SEC-CIK-0000001234")
        self.assertEqual(record["issuer_entity_role"], "SEC_REGISTRANT_LEGAL_ENTITY")

    def test_pilot_complete_is_preserved(self):
        record = self.build()["records"][1]
        self.assertEqual(record["issuer_identity_state"], "PILOT_COMPLETE")
        self.assertEqual(record["issuer_key"], "VANGUARD")

    def test_duplicate_plan_identity_fails_closed(self):
        self.plan["records"][1]["security_id"] = "SEC-US-AAA"
        with self.assertRaises(IssuerLedgerRebuildError):
            self.build()

    def test_duplicate_registry_cik_conflicts(self):
        self.registry["records"].append(copy.deepcopy(self.registry["records"][0]))
        self.assertEqual(self.build()["records"][0]["issuer_identity_state"], "ISSUER_CONFLICTED")

    def test_missing_registry_record_is_unresolved(self):
        self.registry["records"] = []
        self.assertEqual(self.build()["records"][0]["issuer_identity_state"], "ISSUER_UNRESOLVED")

    def test_unconfirmed_registry_record_is_unresolved(self):
        self.registry["records"][0]["state"] = "REGISTRANT_UNRESOLVED"
        self.assertEqual(self.build()["records"][0]["issuer_identity_state"], "ISSUER_UNRESOLVED")

    def test_invalid_lineage_quarantines(self):
        self.registry["records"][0]["payload_sha256"] = "bad"
        self.assertEqual(self.build()["records"][0]["issuer_identity_state"], "ISSUER_QUARANTINED")

    def test_unconfirmed_sec_identity_is_unresolved(self):
        self.sec["records"][0]["resolution_state"] = "UNRESOLVED"
        self.assertEqual(self.build()["records"][0]["issuer_identity_state"], "ISSUER_UNRESOLVED")

    def test_taxonomy_and_production_authority_remain_false(self):
        for record in self.build()["records"]:
            self.assertFalse(record["taxonomy_dimensions_assigned"])
            self.assertFalse(record["production_taxonomy_authority"])

    def test_downstream_authorities_remain_false(self):
        authority = self.build()["authority"]
        for key in ("issuer_batch_planning", "production_taxonomy_classification", "relative_return_calculation", "forecasting", "ranking"):
            self.assertFalse(authority[key])


if __name__ == "__main__":
    unittest.main()
