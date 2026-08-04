from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.infrastructure.full_recent_market_data_collection import (
    FullCollectionValidationError,
    build_completion_summary,
    pending_records,
    replace_checkpoint_record,
    validate_input,
)


POLICY_PATH = Path("config/sources/full_recent_market_data_collection_policy.json")


def record(number: int, symbol: str, status: str | None = None) -> dict:
    value = {"security_id": f"SEC-{number}", "symbol": symbol}
    if status is not None:
        value["collection_status"] = status
    return value


class Phase2B3FullCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.policy["expected_input_record_count"] = 3
        self.inputs = [record(1, "VOO"), record(2, "SCHD"), record(3, "QQQM")]

    def test_policy_preserves_full_input_without_downstream_authority(self) -> None:
        self.assertTrue(self.policy["preserve_all_input_records"])
        self.assertFalse(self.policy["destructive_deletion_allowed"])
        self.assertIsNone(self.policy["target_universe_size"])
        self.assertTrue(all(value is False for value in self.policy["authority"].values()))

    def test_valid_input_passes(self) -> None:
        validate_input(self.inputs, self.policy)

    def test_count_mismatch_fails_closed(self) -> None:
        with self.assertRaises(FullCollectionValidationError):
            validate_input(self.inputs[:2], self.policy)

    def test_missing_seed_fails_closed(self) -> None:
        changed = [record(1, "VOO"), record(2, "SCHD"), record(3, "SPY")]
        with self.assertRaises(FullCollectionValidationError):
            validate_input(changed, self.policy)

    def test_duplicate_identity_fails_closed(self) -> None:
        changed = [record(1, "VOO"), record(1, "SCHD"), record(3, "QQQM")]
        with self.assertRaises(FullCollectionValidationError):
            validate_input(changed, self.policy)

    def test_pending_excludes_completed_records(self) -> None:
        checkpoint = [{**record(1, "VOO"), "collection_status": "COLLECTED"}]
        output = pending_records(
            self.inputs, checkpoint, retry_failed=False, retryable_statuses={"PROVIDER_ERROR"}
        )
        self.assertEqual([item["symbol"] for item in output], ["SCHD", "QQQM"])

    def test_retry_failed_only_requeues_retryable_status(self) -> None:
        checkpoint = [
            {**record(1, "VOO"), "collection_status": "PROVIDER_ERROR"},
            {**record(2, "SCHD"), "collection_status": "NOT_FOUND"},
        ]
        output = pending_records(
            self.inputs, checkpoint, retry_failed=True, retryable_statuses={"PROVIDER_ERROR"}
        )
        self.assertEqual([item["symbol"] for item in output], ["VOO", "QQQM"])

    def test_unknown_checkpoint_identity_fails_closed(self) -> None:
        with self.assertRaises(FullCollectionValidationError):
            pending_records(
                self.inputs,
                [{**record(99, "BAD"), "collection_status": "COLLECTED"}],
                retry_failed=False,
                retryable_statuses={"PROVIDER_ERROR"},
            )

    def test_replacement_does_not_duplicate_security_id(self) -> None:
        prior = [{**record(1, "VOO"), "collection_status": "PROVIDER_ERROR"}]
        output = replace_checkpoint_record(
            prior, {**record(1, "VOO"), "collection_status": "COLLECTED"}
        )
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["collection_status"], "COLLECTED")

    def test_complete_summary_requires_all_records_and_seeds(self) -> None:
        checkpoint = [
            {**item, "collection_status": "COLLECTED"} for item in self.inputs
        ]
        summary = build_completion_summary(
            self.inputs, checkpoint, self.policy, "2026-08-03"
        )
        self.assertTrue(summary["collection_complete"])
        self.assertEqual(summary["completed_unique_records"], 3)
        self.assertEqual(summary["remaining_records"], 0)

    def test_partial_summary_is_not_complete(self) -> None:
        checkpoint = [{**record(1, "VOO"), "collection_status": "COLLECTED"}]
        summary = build_completion_summary(
            self.inputs, checkpoint, self.policy, "2026-08-03"
        )
        self.assertFalse(summary["collection_complete"])
        self.assertEqual(summary["remaining_records"], 2)

    def test_policy_expected_count_is_certified_active_universe(self) -> None:
        actual = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(actual["expected_input_record_count"], 4419)
        self.assertEqual(actual["required_seed_symbols"], ["VOO", "SCHD", "QQQM"])


if __name__ == "__main__":
    unittest.main()
