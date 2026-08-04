from __future__ import annotations

import unittest

from foundation.universe.active_structural_universe import (
    ActiveStructuralUniverseError,
    load_policy,
    promote_active_universe,
)


class Phase2A5ActiveUniverseTests(unittest.TestCase):
    def sample_snapshot(self):
        return {
            "records": [
                {"security_id": "SEC-US-VOO", "symbol": "VOO", "resolution_state": "SEC_IDENTITY_CONFIRMED"},
                {"security_id": "SEC-US-SCHD", "symbol": "SCHD", "resolution_state": "SEC_IDENTITY_CONFIRMED"},
                {"security_id": "SEC-US-QQQM", "symbol": "QQQM", "resolution_state": "SEC_IDENTITY_CONFIRMED"},
                {"security_id": "SEC-US-X", "symbol": "X", "resolution_state": "UNRESOLVED"},
            ]
        }

    def test_policy_is_evidence_sized_and_non_destructive(self):
        policy = load_policy()
        self.assertEqual(policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")
        self.assertIsNone(policy["target_universe_size"])
        self.assertTrue(policy["preserve_full_discovery_universe"])
        self.assertFalse(policy["destructive_deletion_allowed"])

    def test_seed_etfs_are_required(self):
        result = promote_active_universe(self.sample_snapshot())
        self.assertEqual(result["required_seed_symbols"], ["VOO", "SCHD", "QQQM"])

    def test_confirmed_records_are_active(self):
        result = promote_active_universe(self.sample_snapshot())
        self.assertEqual(result["active_structural_records"], 3)
        self.assertTrue(all(record["market_data_collection_authorized"] for record in result["active_records"]))

    def test_unresolved_records_are_research_only(self):
        result = promote_active_universe(self.sample_snapshot())
        record = result["deferred_records"][0]
        self.assertEqual(record["processing_state"], "RESEARCH_ONLY")
        self.assertEqual(record["processing_reason"], "INSUFFICIENT_OFFICIAL_IDENTITY_EVIDENCE")
        self.assertFalse(record["market_data_collection_authorized"])

    def test_downstream_authority_remains_false(self):
        result = promote_active_universe(self.sample_snapshot())
        for record in result["active_records"] + result["deferred_records"]:
            self.assertFalse(record["analytics_authorized"])
            self.assertFalse(record["recommendations_authorized"])
            self.assertFalse(record["uip_export_authorized"])
            self.assertFalse(record["automatic_execution_authorized"])

    def test_missing_seed_fails_closed(self):
        snapshot = self.sample_snapshot()
        snapshot["records"] = [record for record in snapshot["records"] if record["symbol"] != "QQQM"]
        with self.assertRaises(ActiveStructuralUniverseError):
            promote_active_universe(snapshot)

    def test_duplicate_identity_fails_closed(self):
        snapshot = self.sample_snapshot()
        snapshot["records"].append(dict(snapshot["records"][0]))
        with self.assertRaises(ActiveStructuralUniverseError):
            promote_active_universe(snapshot)

    def test_populations_reconcile(self):
        result = promote_active_universe(self.sample_snapshot())
        self.assertEqual(result["active_structural_records"] + result["deferred_research_only_records"], result["total_discovery_records"])

    def test_no_arbitrary_target_is_created(self):
        result = promote_active_universe(self.sample_snapshot())
        self.assertIsNone(result["target_universe_size"])

    def test_full_universe_is_preserved(self):
        result = promote_active_universe(self.sample_snapshot())
        self.assertTrue(result["full_discovery_universe_preserved"])
        self.assertFalse(result["destructive_deletion_allowed"])


if __name__ == "__main__":
    unittest.main()
