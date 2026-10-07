from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from foundation.market.priority_batch_source_acquisition import PriorityBatchSourceAcquisitionError, build_priority_batch_manifest


POLICY = json.loads(Path("config/market/priority_batch_source_acquisition_policy.json").read_text(encoding="utf-8"))


def fixture() -> dict:
    records = []
    ids = []
    for index in range(347):
        security_id = f"SEC-US-T{index:03d}"
        ids.append(security_id)
        records.append({"security_id": security_id, "symbol": f"T{index:03d}", "issuer_key": "SEC-CIK-0001100663", "batch_state": "BATCH_READY"})
    records.extend({"security_id": f"OTHER-{index}", "symbol": f"O{index}", "issuer_key": "OTHER", "batch_state": "BATCH_READY"} for index in range(3112))
    records.extend([
        {"security_id": "SEC-US-VOO", "symbol": "VOO", "issuer_key": "VANGUARD", "batch_state": "PILOT_COMPLETE"},
        {"security_id": "SEC-US-SCHD", "symbol": "SCHD", "issuer_key": "CHARLES_SCHWAB", "batch_state": "PILOT_COMPLETE"},
        {"security_id": "SEC-US-QQQM", "symbol": "QQQM", "issuer_key": "INVESCO", "batch_state": "PILOT_COMPLETE"},
    ])
    return {"records": records, "batches": [{"priority_rank": 1, "issuer_key": "SEC-CIK-0001100663", "issuer_name": "iSHARES TRUST", "security_count": 347, "security_ids": ids}]}


class Phase36B3FTests(unittest.TestCase):
    def test_exact_priority_batch_builds(self):
        result = build_priority_batch_manifest(fixture(), POLICY)
        self.assertEqual(result["manifest_record_count"], 347)
        self.assertTrue(result["manifest_complete"])

    def test_all_records_begin_pending(self):
        result = build_priority_batch_manifest(fixture(), POLICY)
        self.assertEqual(result["acquisition_state_counts"], {"PENDING": 347})

    def test_source_capture_not_executed(self):
        result = build_priority_batch_manifest(fixture(), POLICY)
        self.assertFalse(result["source_capture_executed"])
        self.assertFalse(result["authority"]["authoritative_source_capture"])

    def test_taxonomy_authorities_remain_false(self):
        result = build_priority_batch_manifest(fixture(), POLICY)
        self.assertTrue(all(not record["taxonomy_classification_authorized"] for record in result["records"]))
        self.assertFalse(result["authority"]["production_taxonomy_classification"])

    def test_duplicate_identity_fails_closed(self):
        document = fixture()
        document["records"][1]["security_id"] = document["records"][0]["security_id"]
        with self.assertRaises(PriorityBatchSourceAcquisitionError):
            build_priority_batch_manifest(document, POLICY)

    def test_wrong_rank_fails_closed(self):
        document = fixture()
        document["batches"][0]["priority_rank"] = 2
        with self.assertRaises(PriorityBatchSourceAcquisitionError):
            build_priority_batch_manifest(document, POLICY)

    def test_wrong_issuer_fails_closed(self):
        document = fixture()
        document["batches"][0]["issuer_key"] = "WRONG"
        with self.assertRaises(PriorityBatchSourceAcquisitionError):
            build_priority_batch_manifest(document, POLICY)

    def test_count_drift_fails_closed(self):
        document = fixture()
        document["batches"][0]["security_ids"].pop()
        with self.assertRaises(PriorityBatchSourceAcquisitionError):
            build_priority_batch_manifest(document, POLICY)

    def test_non_ready_member_fails_closed(self):
        document = fixture()
        document["records"][0]["batch_state"] = "ISSUER_QUARANTINED"
        with self.assertRaises(PriorityBatchSourceAcquisitionError):
            build_priority_batch_manifest(document, POLICY)

    def test_policy_is_fail_closed(self):
        self.assertTrue(POLICY["controls"]["exactly_one_priority_batch_authorized"])
        self.assertFalse(POLICY["authority"]["relative_return_calculation"])
        self.assertFalse(POLICY["authority"]["ranking"])


if __name__ == "__main__":
    unittest.main()
