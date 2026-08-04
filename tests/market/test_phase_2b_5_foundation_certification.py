from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from foundation.market.phase_2b_foundation_certification import (
    Phase2BFoundationCertificationError,
    certify_and_publish,
    load_policy,
)


class Phase2B5FoundationCertificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()

    def test_policy_locks_certified_counts(self) -> None:
        self.assertEqual(self.policy["required_total_records"], 4419)
        self.assertEqual(self.policy["phase_3_candidate_record_count"], 3462)

    def test_provisional_records_are_preserved(self) -> None:
        self.assertTrue(self.policy["provisional_records_preserved"])
        self.assertEqual(self.policy["required_state_counts"]["MARKET_DATA_PROVISIONAL"], 442)

    def test_provisional_records_do_not_advance(self) -> None:
        self.assertFalse(self.policy["provisional_records_advance_to_phase_3"])
        self.assertNotIn("MARKET_DATA_PROVISIONAL", self.policy["phase_3_candidate_states"])

    def test_only_eligible_state_advances(self) -> None:
        self.assertEqual(self.policy["phase_3_candidate_states"], ["MARKET_DATA_ELIGIBLE"])

    def test_no_arbitrary_target(self) -> None:
        self.assertIsNone(self.policy["target_universe_size"])
        self.assertEqual(self.policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")

    def test_destructive_deletion_remains_blocked(self) -> None:
        self.assertFalse(self.policy["destructive_deletion_allowed"])

    def test_required_seeds_are_locked(self) -> None:
        self.assertEqual(self.policy["required_seed_symbols"], ["VOO", "SCHD", "QQQM"])
        self.assertEqual(self.policy["required_seed_state"], "MARKET_DATA_ELIGIBLE")

    def test_downstream_authority_remains_false(self) -> None:
        for key, value in self.policy["authority"].items():
            if key != "phase_3_candidate_publication":
                self.assertFalse(value, key)

    def test_required_reason_counts_reconcile(self) -> None:
        self.assertEqual(sum(self.policy["required_reason_counts"].values()), 4419)

    def test_excluded_states_cover_noneligible_population(self) -> None:
        self.assertEqual(
            set(self.policy["excluded_from_phase_3_states"]),
            {"MARKET_DATA_PROVISIONAL", "RESEARCH_ONLY", "QUARANTINED", "BLOCKED"},
        )

    def test_policy_rejects_provisional_promotion(self) -> None:
        weakened = dict(self.policy)
        weakened["provisional_records_advance_to_phase_3"] = True
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "policy.json"
            path.write_text(json.dumps(weakened), encoding="utf-8")
            with self.assertRaises(Phase2BFoundationCertificationError):
                load_policy(path)

    def test_publication_rejects_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            eligibility = root / "eligibility.json"
            summary = root / "summary.json"
            eligibility.write_text(json.dumps({"records": []}), encoding="utf-8")
            summary.write_text(json.dumps({"screen_state_counts": {}}), encoding="utf-8")
            with self.assertRaises(Phase2BFoundationCertificationError):
                certify_and_publish(eligibility, summary, root / "out")


if __name__ == "__main__":
    unittest.main()
