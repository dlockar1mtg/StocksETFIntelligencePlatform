from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from foundation.universe.snapshot import validate_snapshot

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "data" / "universe" / "snapshots" / "2026-08-03" / "robinhood_universe_snapshot.json"
POLICY_PATH = ROOT / "config" / "universe" / "robinhood_snapshot_policy.json"
REGISTRY_PATH = ROOT / "config" / "contracts" / "contract_registry.json"


class Phase166RobinhoodSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_snapshot_contract_is_registered(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        ids = {item["contract_id"] for item in registry["contracts"]}
        self.assertIn("native.robinhood_universe_snapshot", ids)

    def test_policy_is_point_in_time_immutable_and_fail_closed(self) -> None:
        self.assertTrue(self.policy["snapshot_is_point_in_time"])
        self.assertTrue(self.policy["snapshot_is_immutable"])
        self.assertTrue(self.policy["synthetic_or_assumed_broker_evidence_forbidden"])

    def test_structural_snapshot_passes(self) -> None:
        self.assertEqual([], validate_snapshot(self.snapshot))

    def test_seed_securities_are_present(self) -> None:
        ids = {record["security_id"] for record in self.snapshot["records"]}
        self.assertTrue(set(self.policy["seed_security_ids"]).issubset(ids))

    def test_pending_evidence_is_explicit_and_not_promoted(self) -> None:
        for record in self.snapshot["records"]:
            self.assertEqual("PENDING", record["evidence_state"])
            self.assertEqual("UNKNOWN", record["broker_status"])
            self.assertEqual("BLOCKED", record["final_state"])
            self.assertTrue(any("PENDING" in code for code in record["reason_codes"]))

    def test_unknown_broker_status_cannot_be_promoted(self) -> None:
        changed = copy.deepcopy(self.snapshot)
        changed["records"][0]["final_state"] = "BROKER_ELIGIBLE"
        self.assertIn("SEC-US-VOO: unknown broker status promoted", validate_snapshot(changed))

    def test_pending_taxonomy_cannot_be_promoted(self) -> None:
        changed = copy.deepcopy(self.snapshot)
        changed["records"][0]["broker_status"] = "ELIGIBLE"
        changed["records"][0]["final_state"] = "ANALYTICS_ELIGIBLE"
        self.assertIn("SEC-US-VOO: pending taxonomy promoted", validate_snapshot(changed))

    def test_duplicate_identity_is_blocked(self) -> None:
        changed = copy.deepcopy(self.snapshot)
        changed["records"].append(copy.deepcopy(changed["records"][0]))
        self.assertIn("duplicate security_id in snapshot", validate_snapshot(changed))

    def test_counts_must_reconcile(self) -> None:
        changed = copy.deepcopy(self.snapshot)
        changed["counts"]["blocked"] = 2
        self.assertIn("snapshot counts do not reconcile", validate_snapshot(changed))

    def test_snapshot_grants_no_recommendation_or_execution_authority(self) -> None:
        self.assertTrue(self.policy["snapshot_grants_no_recommendation_authority"])
        self.assertTrue(self.policy["snapshot_grants_no_execution_authority"])


if __name__ == "__main__":
    unittest.main()
