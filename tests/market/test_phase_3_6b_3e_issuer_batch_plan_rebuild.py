from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.market.issuer_batch_plan_rebuild import IssuerBatchPlanRebuildError, build_issuer_batch_plan

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config" / "market" / "issuer_batch_plan_rebuild_policy.json").read_text(encoding="utf-8"))


def ledger(records):
    return {"records": records}


class Phase36B3ETests(unittest.TestCase):
    def test_exact_state_contract(self):
        self.assertEqual(POLICY["batch_states"], ["BATCH_READY", "PILOT_COMPLETE", "ISSUER_UNRESOLVED", "ISSUER_CONFLICTED", "ISSUER_QUARANTINED"])

    def test_confirmed_records_form_ranked_batches(self):
        policy = dict(POLICY, required_full_population=4, completed_pilot_count=1)
        result = build_issuer_batch_plan(ledger([
            {"security_id": "A", "symbol": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X", "issuer_name": "X"},
            {"security_id": "B", "symbol": "B", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X", "issuer_name": "X"},
            {"security_id": "C", "symbol": "C", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "Y", "issuer_name": "Y"},
            {"security_id": "P", "symbol": "P", "issuer_identity_state": "PILOT_COMPLETE", "issuer_key": "P"},
        ]), policy)
        self.assertEqual(result["issuer_batch_count"], 2)
        self.assertEqual(result["batches"][0]["issuer_key"], "X")
        self.assertEqual(result["batches"][0]["priority_rank"], 1)

    def test_tie_break_is_deterministic(self):
        policy = dict(POLICY, required_full_population=3, completed_pilot_count=1)
        result = build_issuer_batch_plan(ledger([
            {"security_id": "B", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "B"},
            {"security_id": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "A"},
            {"security_id": "P", "issuer_identity_state": "PILOT_COMPLETE", "issuer_key": "P"},
        ]), policy)
        self.assertEqual([item["issuer_key"] for item in result["batches"]], ["A", "B"])

    def test_duplicate_identity_fails_closed(self):
        policy = dict(POLICY, required_full_population=2, completed_pilot_count=0)
        with self.assertRaises(IssuerBatchPlanRebuildError):
            build_issuer_batch_plan(ledger([
                {"security_id": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X"},
                {"security_id": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X"},
            ]), policy)

    def test_pilot_count_mismatch_fails_closed(self):
        policy = dict(POLICY, required_full_population=1, completed_pilot_count=1)
        with self.assertRaises(IssuerBatchPlanRebuildError):
            build_issuer_batch_plan(ledger([{"security_id": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X"}]), policy)

    def test_unresolved_is_preserved(self):
        policy = dict(POLICY, required_full_population=2, completed_pilot_count=1)
        result = build_issuer_batch_plan(ledger([
            {"security_id": "A", "issuer_identity_state": "ISSUER_UNRESOLVED"},
            {"security_id": "P", "issuer_identity_state": "PILOT_COMPLETE", "issuer_key": "P"},
        ]), policy)
        self.assertEqual(result["blocked_security_count"], 1)
        self.assertFalse(result["batch_plan_complete"])

    def test_source_capture_remains_false(self):
        self.assertFalse(POLICY["authority"]["authoritative_source_capture"])

    def test_downstream_authorities_remain_false(self):
        for key in ("production_taxonomy_classification", "relative_return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations"):
            self.assertFalse(POLICY["authority"][key])

    def test_planning_assigns_no_taxonomy(self):
        policy = dict(POLICY, required_full_population=1, completed_pilot_count=0)
        result = build_issuer_batch_plan(ledger([{"security_id": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X"}]), policy)
        self.assertFalse(result["records"][0]["taxonomy_dimensions_assigned"])
        self.assertFalse(result["records"][0]["production_taxonomy_authority"])

    def test_complete_plan_advances_to_source_acquisition_control(self):
        policy = dict(POLICY, required_full_population=2, completed_pilot_count=1)
        result = build_issuer_batch_plan(ledger([
            {"security_id": "A", "issuer_identity_state": "ISSUER_CONFIRMED", "issuer_key": "X"},
            {"security_id": "P", "issuer_identity_state": "PILOT_COMPLETE", "issuer_key": "P"},
        ]), policy)
        self.assertTrue(result["batch_plan_complete"])
        self.assertEqual(result["next_required_step"], "PRIORITY_BATCH_SOURCE_ACQUISITION_CONTROL")


if __name__ == "__main__":
    unittest.main()
