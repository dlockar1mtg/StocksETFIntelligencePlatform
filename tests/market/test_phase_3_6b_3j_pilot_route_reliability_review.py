from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from foundation.market.pilot_route_reliability_review import review_routes


ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/pilot_route_reliability_review_policy.json").read_text(encoding="utf-8"))


def request(route_type: str, state: str, url: str) -> dict:
    return {
        "route_type": route_type,
        "discovery_state": state,
        "final_url": url,
        "payload_sha256": "a" * 64,
        "retrieved_at_utc": "2026-08-05T00:00:00+00:00",
        "raw_path": "raw/example.bin",
        "capture_authorized": False,
    }


def execution() -> dict:
    records = []
    for index in range(5):
        records.append({
            "security_id": f"US-ETF-{index}",
            "source_capture_authorized": False,
            "discovery_requests": [
                request("SEC_SERIES_CLASS_FILING_DISCOVERY", "PRODUCT_SPECIFIC_RESOLVED", "https://www.sec.gov/cgi-bin/browse-edgar"),
                request("ISHARES_SYMBOL_PRODUCT_DISCOVERY", "DISCOVERY_UNRESOLVED", "https://www.ishares.com/us/search"),
            ],
        })
    return {"records": records}


class Phase36B3JTests(unittest.TestCase):
    def test_sec_route_is_certified(self) -> None:
        review = review_routes(execution(), POLICY)
        self.assertEqual(review["certified_route_types"], ["SEC_SERIES_CLASS_FILING_DISCOVERY"])

    def test_ishares_route_is_suspended(self) -> None:
        review = review_routes(execution(), POLICY)
        self.assertEqual(review["suspended_route_types"], ["ISHARES_SYMBOL_PRODUCT_DISCOVERY"])

    def test_capture_execution_remains_false(self) -> None:
        review = review_routes(execution(), POLICY)
        self.assertFalse(review["priority_batch_source_capture_authorized"])

    def test_downstream_authorities_remain_false(self) -> None:
        review = review_routes(execution(), POLICY)
        self.assertFalse(review["taxonomy_evidence_normalization_authorized"])
        self.assertFalse(review["production_taxonomy_classification_authorized"])

    def test_count_drift_fails_closed(self) -> None:
        data = execution()
        data["records"].pop()
        with self.assertRaises(ValueError):
            review_routes(data, POLICY)

    def test_duplicate_identity_fails_closed(self) -> None:
        data = execution()
        data["records"][1]["security_id"] = data["records"][0]["security_id"]
        with self.assertRaises(ValueError):
            review_routes(data, POLICY)

    def test_missing_lineage_fails_closed(self) -> None:
        data = execution()
        data["records"][0]["discovery_requests"][0]["payload_sha256"] = None
        with self.assertRaises(ValueError):
            review_routes(data, POLICY)

    def test_premature_capture_authority_fails_closed(self) -> None:
        data = execution()
        data["records"][0]["discovery_requests"][0]["capture_authorized"] = True
        with self.assertRaises(ValueError):
            review_routes(data, POLICY)

    def test_partial_success_is_rejected(self) -> None:
        data = execution()
        data["records"][0]["discovery_requests"][0]["discovery_state"] = "DISCOVERY_UNRESOLVED"
        review = review_routes(data, POLICY)
        sec = next(r for r in review["route_reviews"] if r["route_type"].startswith("SEC_"))
        self.assertEqual(sec["decision"], "REJECTED")

    def test_next_step_is_controlled_capture_plan(self) -> None:
        review = review_routes(execution(), POLICY)
        self.assertEqual(review["next_required_step"], "PRIORITY_BATCH_CONTROLLED_SOURCE_CAPTURE_PLAN")


if __name__ == "__main__":
    unittest.main()
