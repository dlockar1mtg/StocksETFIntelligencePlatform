from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.market.priority_batch_route_discovery_pilot import (
    PriorityBatchRouteDiscoveryPilotError,
    build_route_discovery_pilot,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/priority_batch_route_discovery_pilot_policy.json").read_text(encoding="utf-8"))


def route_record(index: int) -> dict:
    symbol = f"T{index:03d}"
    return {
        "security_id": f"US-ETF-{symbol}",
        "symbol": symbol,
        "route_state": "ROUTE_CANDIDATE_READY",
        "sec_cik": "0001100663",
        "sec_series_id": f"S{index:010d}",
        "sec_class_contract_id": f"C{index:010d}",
        "candidate_routes": [
            {
                "route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
                "source_tier": "SEC_FILING",
                "official_domain": "sec.gov",
                "identity_markers": {"symbol": symbol},
                "capture_authorized": False,
                "route_resolution_required": True,
            },
            {
                "route_type": "ISHARES_SYMBOL_PRODUCT_DISCOVERY",
                "source_tier": "ISSUER_PRODUCT_PAGE",
                "official_domain": "ishares.com",
                "identity_markers": {"symbol": symbol},
                "capture_authorized": False,
                "route_resolution_required": True,
            },
        ],
    }


def ledger() -> dict:
    return {
        "route_coverage_complete": True,
        "records": [route_record(index) for index in range(347)],
    }


class Phase36B3HTests(unittest.TestCase):
    def test_policy_is_fail_closed(self) -> None:
        self.assertTrue(POLICY["authority"]["route_discovery_pilot_manifest_build"])
        self.assertFalse(POLICY["authority"]["route_discovery_pilot_execution"])
        self.assertFalse(POLICY["authority"]["production_taxonomy_classification"])

    def test_deterministic_stratified_sample_builds(self) -> None:
        result = build_route_discovery_pilot(ledger(), POLICY)
        self.assertEqual(result["pilot_record_count"], 5)
        self.assertEqual(result["pilot_state_counts"], {"DISCOVERY_PENDING": 5})
        self.assertEqual(result["records"][0]["security_id"], "US-ETF-T000")
        self.assertEqual(result["records"][-1]["security_id"], "US-ETF-T346")

    def test_each_record_has_two_requests(self) -> None:
        result = build_route_discovery_pilot(ledger(), POLICY)
        self.assertTrue(all(len(record["discovery_requests"]) == 2 for record in result["records"]))

    def test_requests_are_not_capture_authority(self) -> None:
        result = build_route_discovery_pilot(ledger(), POLICY)
        for record in result["records"]:
            self.assertFalse(record["source_capture_authorized"])
            for request in record["discovery_requests"]:
                self.assertFalse(request["capture_authorized"])
                self.assertIsNone(request["resolved_url"])
                self.assertIsNone(request["payload_sha256"])

    def test_count_drift_fails_closed(self) -> None:
        source = ledger()
        source["records"].pop()
        with self.assertRaisesRegex(PriorityBatchRouteDiscoveryPilotError, "ROUTE_POPULATION_COUNT_MISMATCH"):
            build_route_discovery_pilot(source, POLICY)

    def test_duplicate_identity_fails_closed(self) -> None:
        source = ledger()
        source["records"][1]["security_id"] = source["records"][0]["security_id"]
        with self.assertRaisesRegex(PriorityBatchRouteDiscoveryPilotError, "DUPLICATE_OR_MISSING_SECURITY_ID"):
            build_route_discovery_pilot(source, POLICY)

    def test_incomplete_coverage_fails_closed(self) -> None:
        source = ledger()
        source["route_coverage_complete"] = False
        with self.assertRaisesRegex(PriorityBatchRouteDiscoveryPilotError, "ROUTE_COVERAGE_NOT_COMPLETE"):
            build_route_discovery_pilot(source, POLICY)

    def test_nonready_selected_route_fails_closed(self) -> None:
        source = ledger()
        source["records"][0]["route_state"] = "ROUTE_UNRESOLVED"
        with self.assertRaisesRegex(PriorityBatchRouteDiscoveryPilotError, "PILOT_ROUTE_NOT_READY"):
            build_route_discovery_pilot(source, POLICY)

    def test_route_contract_mismatch_fails_closed(self) -> None:
        source = ledger()
        source["records"][0]["candidate_routes"][0]["route_type"] = "UNKNOWN"
        with self.assertRaisesRegex(PriorityBatchRouteDiscoveryPilotError, "ROUTE_TYPE_CONTRACT_MISMATCH"):
            build_route_discovery_pilot(source, POLICY)

    def test_downstream_authorities_remain_false(self) -> None:
        result = build_route_discovery_pilot(ledger(), POLICY)
        for key in (
            "priority_batch_source_capture",
            "production_taxonomy_classification",
            "relative_return_calculation",
            "forecasting",
            "ranking",
            "recommendations",
            "uip_export",
        ):
            self.assertFalse(result["authority"][key])


if __name__ == "__main__":
    unittest.main()
