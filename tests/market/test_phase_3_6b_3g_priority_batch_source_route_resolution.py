from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from foundation.market.priority_batch_source_route_resolution import (
    PriorityBatchRouteError,
    build_priority_batch_route_ledger,
)


POLICY = json.loads(Path("config/market/priority_batch_source_route_resolution_policy.json").read_text(encoding="utf-8"))


def manifest(count: int = 347):
    return {"records": [{"security_id": f"US-ETF-{i}", "symbol": f"T{i}", "issuer_key": POLICY["selected_issuer_key"], "acquisition_state": "PENDING"} for i in range(count)]}


def identities(count: int = 347):
    return {"records": [{"security_id": f"US-ETF-{i}", "resolution_state": "SEC_IDENTITY_CONFIRMED", "sec_cik": "1100663", "sec_series_id": f"S{i}", "sec_class_contract_id": f"C{i}"} for i in range(count)]}


class Phase36B3GTests(unittest.TestCase):
    def test_complete_identity_builds_candidates(self):
        result = build_priority_batch_route_ledger(manifest(), identities(), POLICY)
        self.assertEqual(result["route_state_counts"], {"ROUTE_CANDIDATE_READY": 347})
        self.assertTrue(result["route_coverage_complete"])

    def test_candidate_routes_are_not_capture_authority(self):
        result = build_priority_batch_route_ledger(manifest(), identities(), POLICY)
        record = result["records"][0]
        self.assertFalse(record["source_capture_authorized"])
        self.assertTrue(all(not route["capture_authorized"] for route in record["candidate_routes"]))

    def test_exact_official_domains(self):
        self.assertEqual(POLICY["official_domains"], ["sec.gov", "ishares.com", "blackrock.com"])

    def test_missing_sec_identity_is_unresolved(self):
        result = build_priority_batch_route_ledger(manifest(), {"records": []}, POLICY)
        self.assertEqual(result["records"][0]["route_state"], "ROUTE_UNRESOLVED")

    def test_duplicate_sec_identity_is_conflicted(self):
        source = identities()
        source["records"].append(deepcopy(source["records"][0]))
        result = build_priority_batch_route_ledger(manifest(), source, POLICY)
        self.assertEqual(result["records"][0]["route_state"], "ROUTE_CONFLICTED")

    def test_incomplete_series_class_is_quarantined(self):
        source = identities()
        source["records"][0]["sec_class_contract_id"] = None
        result = build_priority_batch_route_ledger(manifest(), source, POLICY)
        self.assertEqual(result["records"][0]["route_state"], "ROUTE_QUARANTINED")

    def test_nonpending_manifest_record_is_quarantined(self):
        source = manifest()
        source["records"][0]["acquisition_state"] = "SOURCE_CAPTURED"
        result = build_priority_batch_route_ledger(source, identities(), POLICY)
        self.assertEqual(result["records"][0]["route_state"], "ROUTE_QUARANTINED")

    def test_count_drift_fails_closed(self):
        with self.assertRaises(PriorityBatchRouteError):
            build_priority_batch_route_ledger(manifest(346), identities(346), POLICY)

    def test_duplicate_manifest_identity_fails_closed(self):
        source = manifest()
        source["records"][1]["security_id"] = source["records"][0]["security_id"]
        with self.assertRaises(PriorityBatchRouteError):
            build_priority_batch_route_ledger(source, identities(), POLICY)

    def test_downstream_authorities_remain_false(self):
        blocked = ["priority_batch_source_capture", "production_taxonomy_classification", "relative_return_calculation", "forecasting", "ranking"]
        self.assertTrue(all(POLICY["authority"][name] is False for name in blocked))


if __name__ == "__main__":
    unittest.main()
