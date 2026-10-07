import json
import unittest
from pathlib import Path

from foundation.market.evidence_backed_issuer_identity import IssuerIdentityError, build_issuer_identity_ledger

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/evidence_backed_issuer_identity_policy.json").read_text())


def plan_record(security_id="SEC-US-AAA", symbol="AAA"):
    return {"security_id": security_id, "symbol": symbol}


def sec_record(security_id="SEC-US-AAA", status="SEC_IDENTITY_CONFIRMED"):
    return {
        "security_id": security_id,
        "symbol": "AAA",
        "resolution_state": status,
        "registrant_name": "Example ETF Trust",
        "registrant_cik": "123456",
        "source_record_id": "SEC-AAA",
    }


class Phase36B3DIssuerIdentityTests(unittest.TestCase):
    def policy(self, count=1):
        policy = dict(POLICY)
        policy["required_full_population"] = count
        policy["completed_pilot_count"] = 0
        return policy

    def test_confirmed_sec_identity_creates_issuer(self):
        result = build_issuer_identity_ledger([plan_record()], [sec_record()], [], self.policy())
        self.assertEqual(result["records"][0]["issuer_identity_state"], "ISSUER_CONFIRMED")
        self.assertEqual(result["records"][0]["issuer_key"], "SEC-CIK-0000123456")

    def test_missing_sec_record_is_unresolved(self):
        result = build_issuer_identity_ledger([plan_record()], [], [], self.policy())
        self.assertEqual(result["records"][0]["issuer_identity_state"], "ISSUER_UNRESOLVED")

    def test_unconfirmed_sec_record_is_unresolved(self):
        result = build_issuer_identity_ledger([plan_record()], [sec_record(status="UNMATCHED")], [], self.policy())
        self.assertEqual(result["records"][0]["issuer_identity_state"], "ISSUER_UNRESOLVED")

    def test_duplicate_sec_identity_is_conflicted(self):
        result = build_issuer_identity_ledger([plan_record()], [sec_record(), sec_record()], [], self.policy())
        self.assertEqual(result["records"][0]["issuer_identity_state"], "ISSUER_CONFLICTED")

    def test_missing_issuer_fields_quarantines(self):
        record = sec_record()
        record["registrant_name"] = None
        result = build_issuer_identity_ledger([plan_record()], [record], [], self.policy())
        self.assertEqual(result["records"][0]["issuer_identity_state"], "ISSUER_QUARANTINED")

    def test_pilot_complete_is_preserved(self):
        pilot = {"security_id": "SEC-US-AAA", "symbol": "AAA", "classification_status": "CLASSIFIED", "issuer_key": "TEST", "source_tier": "SEC_FILING", "source_record_id": "X"}
        result = build_issuer_identity_ledger([plan_record()], [], [pilot], self.policy())
        self.assertEqual(result["records"][0]["issuer_identity_state"], "PILOT_COMPLETE")

    def test_duplicate_plan_identity_fails_closed(self):
        with self.assertRaises(IssuerIdentityError):
            build_issuer_identity_ledger([plan_record(), plan_record()], [], [], self.policy(2))

    def test_taxonomy_authority_remains_false(self):
        result = build_issuer_identity_ledger([plan_record()], [sec_record()], [], self.policy())
        self.assertFalse(result["records"][0]["taxonomy_dimensions_assigned"])
        self.assertFalse(result["records"][0]["production_taxonomy_authority"])

    def test_state_contract_is_exact(self):
        self.assertEqual(POLICY["identity_states"], ["ISSUER_CONFIRMED", "ISSUER_UNRESOLVED", "ISSUER_CONFLICTED", "ISSUER_QUARANTINED", "PILOT_COMPLETE"])

    def test_downstream_authorities_remain_false(self):
        for key in ("issuer_batch_planning", "authoritative_source_capture", "production_taxonomy_classification", "relative_return_calculation", "risk_analytics", "forecasting", "ranking"):
            self.assertFalse(POLICY["authority"][key])


if __name__ == "__main__":
    unittest.main()
