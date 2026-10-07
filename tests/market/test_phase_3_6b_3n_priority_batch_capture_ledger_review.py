from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.priority_batch_capture_ledger_review import (
    review_capture_ledger,
    write_review,
)


class Phase36B3NTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.policy = {
            "required_input_phase": "3.6b.3m",
            "required_record_count": 2,
            "required_route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
            "thresholds": {
                "minimum_product_specific_rate_for_certification": 1.0,
                "maximum_shared_payload_group_size_for_product_specific": 1,
                "required_raw_hash_coverage": 1.0,
                "required_identity_marker_coverage": 1.0,
            },
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _record(self, index: int, payload: bytes) -> dict:
        security_id = f"US-ETF-T{index}"
        raw = self.root / f"{security_id}.bin"
        raw.write_bytes(payload)
        return {
            "sequence": index,
            "security_id": security_id,
            "symbol": f"T{index}",
            "sec_cik": "0001100663",
            "sec_series_id": f"S00000000{index}",
            "sec_class_contract_id": f"C00000000{index}",
            "route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
            "capture_state": "CAPTURED",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "raw_path": str(raw),
        }

    def _ledger(self, records: list[dict]) -> dict:
        return {
            "phase": "3.6b.3m",
            "capture_ledger_complete": True,
            "final_record_count": len(records),
            "records": records,
        }

    def test_unique_product_specific_payloads_are_eligible(self) -> None:
        one = b"CIK 0001100663 S000000001 C000000001 T1"
        two = b"CIK 0001100663 S000000002 C000000002 T2"
        review = review_capture_ledger(
            self._ledger([self._record(1, one), self._record(2, two)]),
            self.policy,
            self.root,
        )
        self.assertTrue(review["capture_ledger_certification_authorized"])
        self.assertEqual(review["product_specific_evidence_count"], 2)

    def test_shared_payload_is_generic_and_fails_closed(self) -> None:
        payload = b"generic SEC browse page"
        review = review_capture_ledger(
            self._ledger([self._record(1, payload), self._record(2, payload)]),
            self.policy,
            self.root,
        )
        self.assertFalse(review["capture_ledger_certification_authorized"])
        self.assertEqual(review["review_state_counts"]["GENERIC_SHARED_PAYLOAD"], 2)

    def test_http_capture_state_is_not_enough(self) -> None:
        payload = b"unique but missing all expected markers"
        review = review_capture_ledger(
            self._ledger([self._record(1, payload), self._record(2, payload + b"x")]),
            self.policy,
            self.root,
        )
        self.assertEqual(review["product_specific_evidence_count"], 0)

    def test_missing_raw_evidence_is_preserved(self) -> None:
        record = self._record(1, b"payload")
        Path(record["raw_path"]).unlink()
        second = self._record(2, b"different")
        review = review_capture_ledger(self._ledger([record, second]), self.policy, self.root)
        self.assertEqual(review["records"][0]["review_state"], "RAW_EVIDENCE_MISSING")

    def test_hash_mismatch_is_quarantined(self) -> None:
        record = self._record(1, b"payload")
        record["payload_sha256"] = "0" * 64
        second = self._record(2, b"different")
        review = review_capture_ledger(self._ledger([record, second]), self.policy, self.root)
        self.assertEqual(review["records"][0]["review_state"], "RAW_HASH_MISMATCH")

    def test_duplicate_identity_fails_closed(self) -> None:
        one = self._record(1, b"one")
        two = dict(one)
        with self.assertRaises(ValueError):
            review_capture_ledger(self._ledger([one, two]), self.policy, self.root)

    def test_population_drift_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            review_capture_ledger(self._ledger([self._record(1, b"one")]), self.policy, self.root)

    def test_uncertified_route_fails_closed(self) -> None:
        one = self._record(1, b"one")
        two = self._record(2, b"two")
        one["route_type"] = "ISHARES_SYMBOL_PRODUCT_DISCOVERY"
        with self.assertRaises(ValueError):
            review_capture_ledger(self._ledger([one, two]), self.policy, self.root)

    def test_downstream_authority_remains_false(self) -> None:
        one = b"0001100663 S000000001 C000000001 T1"
        two = b"0001100663 S000000002 C000000002 T2"
        review = review_capture_ledger(
            self._ledger([self._record(1, one), self._record(2, two)]),
            self.policy,
            self.root,
        )
        self.assertFalse(review["taxonomy_evidence_normalization_authorized"])
        self.assertFalse(review["production_taxonomy_classification_authorized"])

    def test_summary_contains_hash_and_next_step(self) -> None:
        payload = b"generic"
        review = review_capture_ledger(
            self._ledger([self._record(1, payload), self._record(2, payload)]),
            self.policy,
            self.root,
        )
        output = self.root / "review.json"
        summary = self.root / "summary.json"
        result = write_review(review, output, summary)
        self.assertRegex(result["review_ledger_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            result["next_required_step"],
            "SEC_PRODUCT_SPECIFIC_FILING_DOCUMENT_ROUTE_REMEDIATION",
        )


if __name__ == "__main__":
    unittest.main()
