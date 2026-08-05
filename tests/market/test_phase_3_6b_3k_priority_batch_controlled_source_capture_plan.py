from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.priority_batch_controlled_source_capture_plan import (
    build_capture_plan,
    write_outputs,
)


POLICY_PATH = Path("config/market/priority_batch_controlled_source_capture_plan_policy.json")


def _policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _route_record(index: int) -> dict:
    security_id = f"US-ETF-T{index:03d}"
    return {
        "security_id": security_id,
        "symbol": f"T{index:03d}",
        "issuer_key": "SEC-CIK-0001100663",
        "sec_cik": "0001100663",
        "sec_series_id": f"S{index:09d}",
        "sec_class_contract_id": f"C{index:09d}",
        "route_state": "ROUTE_CANDIDATE_READY",
        "candidate_routes": [
            {
                "route_type": "ISHARES_SYMBOL_PRODUCT_DISCOVERY",
                "official_domain": "ishares.com",
                "capture_authorized": False,
            },
            {
                "route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
                "official_domain": "sec.gov",
                "capture_authorized": False,
            },
        ],
    }


def _route_ledger(count: int = 347) -> dict:
    return {
        "selected_priority_rank": 1,
        "selected_issuer_key": "SEC-CIK-0001100663",
        "selected_issuer_name": "iSHARES TRUST",
        "route_coverage_complete": True,
        "source_capture_executed": False,
        "records": [_route_record(index) for index in range(1, count + 1)],
    }


def _review() -> dict:
    return {
        "certified_route_types": ["SEC_SERIES_CLASS_FILING_DISCOVERY"],
        "suspended_route_types": ["ISHARES_SYMBOL_PRODUCT_DISCOVERY"],
        "controlled_batch_capture_plan_authorized": True,
        "priority_batch_source_capture_authorized": False,
    }


class Phase36B3KTests(unittest.TestCase):
    def test_plan_builds_full_deterministic_population(self) -> None:
        plan = build_capture_plan(_route_ledger(), _review(), _policy(), "2026-08-05")
        self.assertEqual(plan["plan_record_count"], 347)
        self.assertTrue(plan["capture_plan_complete"])
        self.assertEqual(plan["records"][0]["sequence"], 1)
        self.assertEqual(plan["records"][-1]["sequence"], 347)

    def test_count_drift_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_capture_plan(_route_ledger(346), _review(), _policy(), "2026-08-05")

    def test_duplicate_identity_fails_closed(self) -> None:
        ledger = _route_ledger()
        ledger["records"][1]["security_id"] = ledger["records"][0]["security_id"]
        with self.assertRaises(ValueError):
            build_capture_plan(ledger, _review(), _policy(), "2026-08-05")

    def test_uncertified_route_fails_closed(self) -> None:
        review = _review()
        review["certified_route_types"] = ["ISHARES_SYMBOL_PRODUCT_DISCOVERY"]
        with self.assertRaises(ValueError):
            build_capture_plan(_route_ledger(), review, _policy(), "2026-08-05")

    def test_suspended_route_must_remain_excluded(self) -> None:
        review = _review()
        review["suspended_route_types"] = []
        with self.assertRaises(ValueError):
            build_capture_plan(_route_ledger(), review, _policy(), "2026-08-05")

    def test_plan_records_are_pending_without_capture_evidence(self) -> None:
        plan = build_capture_plan(_route_ledger(), _review(), _policy(), "2026-08-05")
        for record in plan["records"]:
            self.assertEqual(record["capture_state"], "CAPTURE_PENDING")
            self.assertEqual(record["attempt_count"], 0)
            self.assertIsNone(record["payload_sha256"])
            self.assertFalse(record["capture_authorized"])

    def test_request_urls_and_raw_paths_are_governed(self) -> None:
        plan = build_capture_plan(_route_ledger(), _review(), _policy(), "2026-08-05")
        record = plan["records"][0]
        self.assertTrue(record["request_url"].startswith("https://www.sec.gov/"))
        self.assertIn(record["sec_series_id"], record["request_url"])
        self.assertIn(record["security_id"], record["raw_path"])
        self.assertIn("2026-08-05", record["raw_path"])

    def test_execution_and_downstream_authorities_remain_false(self) -> None:
        plan = build_capture_plan(_route_ledger(), _review(), _policy(), "2026-08-05")
        self.assertFalse(plan["capture_execution_performed"])
        for authority in (
            "priority_batch_source_capture",
            "authoritative_source_capture",
            "taxonomy_evidence_normalization",
            "production_taxonomy_classification",
            "relative_return_calculation",
            "forecasting",
            "ranking",
            "uip_export",
        ):
            self.assertFalse(plan["authority"][authority])

    def test_missing_sec_identity_fails_closed(self) -> None:
        ledger = _route_ledger()
        ledger["records"][0]["sec_series_id"] = None
        with self.assertRaises(ValueError):
            build_capture_plan(ledger, _review(), _policy(), "2026-08-05")

    def test_outputs_include_hash_and_next_step(self) -> None:
        plan = build_capture_plan(_route_ledger(), _review(), _policy(), "2026-08-05")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            summary = Path(directory) / "summary.json"
            result = write_outputs(plan, output, summary)
            self.assertRegex(result["capture_plan_sha256"], r"^[a-f0-9]{64}$")
            self.assertEqual(
                result["next_required_step"],
                "PRIORITY_BATCH_CONTROLLED_SOURCE_CAPTURE_PLAN_CERTIFICATION",
            )


if __name__ == "__main__":
    unittest.main()
