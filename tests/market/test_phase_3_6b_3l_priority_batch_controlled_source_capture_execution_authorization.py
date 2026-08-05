from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from foundation.market.priority_batch_controlled_source_capture_execution_authorization import (
    build_authorization,
    validate_capture_plan,
)


class Phase36B3LTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.policy = json.loads((root / "config/market/priority_batch_controlled_source_capture_execution_authorization_policy.json").read_text(encoding="utf-8"))
        self.plan_path = root / "data/staged/priority_batch_controlled_source_capture_plan/2026-08-05/priority_batch_controlled_source_capture_plan.json"
        if self.plan_path.exists():
            self.plan_bytes = self.plan_path.read_bytes()
            self.plan = json.loads(self.plan_bytes.decode("utf-8"))
        else:
            self.plan = self._fixture_plan()
            self.plan_bytes = json.dumps(self.plan, indent=2, sort_keys=True).encode("utf-8")
            self.policy = deepcopy(self.policy)
            import hashlib
            self.policy["required_capture_plan_sha256"] = hashlib.sha256(self.plan_bytes).hexdigest()

    def _fixture_plan(self):
        records = []
        for index in range(1, 348):
            sid = f"US-ETF-T{index:03d}"
            records.append({
                "sequence": index,
                "security_id": sid,
                "symbol": f"T{index:03d}",
                "sec_cik": "0001100663",
                "sec_series_id": f"S{index:09d}",
                "sec_class_contract_id": f"C{index:09d}",
                "expected_identity_markers": [f"S{index:09d}", f"C{index:09d}", f"T{index:03d}"],
                "capture_state": "CAPTURE_PENDING",
                "attempt_count": 0,
                "route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
                "official_domain": "sec.gov",
                "request_url": f"https://www.sec.gov/cgi-bin/browse-edgar?series=S{index:09d}&class=C{index:09d}",
                "raw_path": f"data/raw/priority_batch_sec_capture/2026-08-05/{sid}/sec_series_class_filing.bin",
                "http_status": None,
                "final_url": None,
                "redirect_chain": [],
                "retrieved_at_utc": None,
                "payload_sha256": None,
                "failure_reason": None,
                "capture_authorized": False,
                "taxonomy_dimensions_assigned": False,
                "taxonomy_classification_authorized": False,
                "production_taxonomy_authority": False,
            })
        return {
            "phase": "3.6b.3k",
            "required_record_count": 347,
            "plan_record_count": 347,
            "capture_plan_complete": True,
            "capture_execution_performed": False,
            "certified_route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
            "suspended_route_type": "ISHARES_SYMBOL_PRODUCT_DISCOVERY",
            "execution_contract": {
                "ordering": "SEC_SERIES_ID_THEN_CLASS_CONTRACT_ID_THEN_SECURITY_ID",
                "maximum_requests_per_second": 1,
                "maximum_retry_attempts": 2,
                "request_timeout_seconds": 45,
                "checkpoint_after_each_record": True,
                "resume_safe": True,
                "immutable_raw_storage": True,
            },
            "records": records,
        }

    def test_valid_plan_authorizes_controlled_capture(self):
        result = build_authorization(self.plan, self.policy, self.plan_bytes)
        self.assertTrue(result["capture_execution_authorized"])
        self.assertFalse(result["automatic_execution_authorized"])

    def test_hash_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_capture_plan(self.plan, self.policy, self.plan_bytes + b"x")

    def test_count_drift_fails_closed(self):
        altered = deepcopy(self.plan); altered["plan_record_count"] = 346
        with self.assertRaises(ValueError): validate_capture_plan(altered, self.policy, self.plan_bytes)

    def test_duplicate_identity_fails_closed(self):
        altered = deepcopy(self.plan); altered["records"][1]["security_id"] = altered["records"][0]["security_id"]
        payload = json.dumps(altered, indent=2, sort_keys=True).encode(); policy = deepcopy(self.policy)
        import hashlib; policy["required_capture_plan_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError): validate_capture_plan(altered, policy, payload)

    def test_noncontiguous_sequence_fails_closed(self):
        altered = deepcopy(self.plan); altered["records"][0]["sequence"] = 2
        payload = json.dumps(altered, indent=2, sort_keys=True).encode(); policy = deepcopy(self.policy)
        import hashlib; policy["required_capture_plan_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError): validate_capture_plan(altered, policy, payload)

    def test_uncertified_route_fails_closed(self):
        altered = deepcopy(self.plan); altered["records"][0]["route_type"] = "ISHARES_SYMBOL_PRODUCT_DISCOVERY"
        payload = json.dumps(altered, indent=2, sort_keys=True).encode(); policy = deepcopy(self.policy)
        import hashlib; policy["required_capture_plan_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError): validate_capture_plan(altered, policy, payload)

    def test_nonofficial_url_fails_closed(self):
        altered = deepcopy(self.plan); altered["records"][0]["request_url"] = "https://example.com/x"
        payload = json.dumps(altered, indent=2, sort_keys=True).encode(); policy = deepcopy(self.policy)
        import hashlib; policy["required_capture_plan_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError): validate_capture_plan(altered, policy, payload)

    def test_duplicate_raw_path_fails_closed(self):
        altered = deepcopy(self.plan); altered["records"][1]["raw_path"] = altered["records"][0]["raw_path"]
        payload = json.dumps(altered, indent=2, sort_keys=True).encode(); policy = deepcopy(self.policy)
        import hashlib; policy["required_capture_plan_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError): validate_capture_plan(altered, policy, payload)

    def test_premature_capture_evidence_fails_closed(self):
        altered = deepcopy(self.plan); altered["records"][0]["http_status"] = 200
        payload = json.dumps(altered, indent=2, sort_keys=True).encode(); policy = deepcopy(self.policy)
        import hashlib; policy["required_capture_plan_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError): validate_capture_plan(altered, policy, payload)

    def test_downstream_authorities_remain_false(self):
        result = build_authorization(self.plan, self.policy, self.plan_bytes)
        self.assertFalse(result["taxonomy_evidence_normalization_authorized"])
        self.assertFalse(result["production_taxonomy_classification_authorized"])


if __name__ == "__main__":
    unittest.main()
