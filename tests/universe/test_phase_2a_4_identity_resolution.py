from __future__ import annotations

import unittest

from foundation.universe.structural_identity_resolution import (
    StructuralIdentityResolutionError,
    attribute_unmatched,
    load_policy,
    resolve_identities,
)


class Phase2A4IdentityResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.universe = [
            {"security_id": "SEC-US-VOO", "symbol": "VOO", "issuer_name": "Vanguard"},
            {"security_id": "SEC-US-GLD", "symbol": "GLD", "name": "SPDR Gold Trust"},
            {"security_id": "SEC-US-ETN", "symbol": "ETN1", "name": "Example Exchange Traded Note"},
            {"security_id": "SEC-US-ABC", "symbol": "ABC.A", "issuer_name": "Example"},
        ]
        self.reconciliation = {
            "records": [
                {
                    "security_id": "SEC-US-VOO", "symbol": "VOO", "reconciliation_state": "MATCHED",
                    "sec_cik": "0000036405", "sec_series_id": "S000002839",
                    "sec_class_contract_id": "C000092055", "sec_fund_name": "Vanguard 500 Index Fund",
                },
                {"security_id": "SEC-US-GLD", "symbol": "GLD", "reconciliation_state": "UNMATCHED"},
                {"security_id": "SEC-US-ETN", "symbol": "ETN1", "reconciliation_state": "UNMATCHED"},
                {"security_id": "SEC-US-ABC", "symbol": "ABC.A", "reconciliation_state": "UNMATCHED"},
            ]
        }

    def test_policy_is_evidence_sized_and_non_destructive(self) -> None:
        policy = load_policy()
        self.assertEqual(policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")
        self.assertIsNone(policy["target_universe_size"])
        self.assertTrue(policy["preserve_full_discovery_universe"])
        self.assertFalse(policy["destructive_deletion_allowed"])

    def test_policy_grants_no_downstream_authority(self) -> None:
        policy = load_policy()
        for key, value in policy["authority"].items():
            if key.endswith("development"):
                continue
            self.assertFalse(value, key)

    def test_unique_sec_match_is_confirmed(self) -> None:
        result = resolve_identities(self.reconciliation, self.universe)
        record = result["matched_records"][0]
        self.assertEqual(record["resolution_state"], "SEC_IDENTITY_CONFIRMED")
        self.assertEqual(record["sec_cik"], "0000036405")

    def test_specialized_trust_is_attributed(self) -> None:
        reason, state, evidence = attribute_unmatched(self.universe[1])
        self.assertEqual(reason, "SPECIALIZED_TRUST")
        self.assertEqual(state, "SPECIALIZED")
        self.assertTrue(evidence)

    def test_etn_is_alternate_structure(self) -> None:
        reason, state, _ = attribute_unmatched(self.universe[2])
        self.assertEqual(reason, "ETN_OR_DEBT_SECURITY")
        self.assertEqual(state, "ALTERNATE_STRUCTURE_CONFIRMED")

    def test_symbol_normalization_is_preserved_for_followup(self) -> None:
        reason, state, _ = attribute_unmatched(self.universe[3])
        self.assertEqual(reason, "SYMBOL_NORMALIZATION_REQUIRED")
        self.assertEqual(state, "REQUIRES_ADDITIONAL_SOURCE")

    def test_full_universe_is_preserved(self) -> None:
        result = resolve_identities(self.reconciliation, self.universe)
        self.assertEqual(result["total_records"], len(self.universe))
        self.assertEqual(len(result["records"]), len(self.universe))
        self.assertTrue(result["full_discovery_universe_preserved"])

    def test_resolution_grants_no_downstream_authority(self) -> None:
        result = resolve_identities(self.reconciliation, self.universe)
        for record in result["records"]:
            self.assertFalse(record["analytics_authorized"])
            self.assertFalse(record["recommendations_authorized"])
            self.assertFalse(record["uip_export_authorized"])
            self.assertFalse(record["automatic_execution_authorized"])

    def test_incomplete_matched_identity_fails_closed(self) -> None:
        broken = {"records": [dict(item) for item in self.reconciliation["records"]]}
        broken["records"][0]["sec_series_id"] = None
        with self.assertRaises(StructuralIdentityResolutionError):
            resolve_identities(broken, self.universe)

    def test_count_or_identity_mismatch_fails_closed(self) -> None:
        with self.assertRaises(StructuralIdentityResolutionError):
            resolve_identities({"records": self.reconciliation["records"][:-1]}, self.universe)


if __name__ == "__main__":
    unittest.main()
