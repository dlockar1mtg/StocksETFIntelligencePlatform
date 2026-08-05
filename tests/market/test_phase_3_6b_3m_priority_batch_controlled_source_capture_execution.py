from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from foundation.market.priority_batch_controlled_source_capture_execution import (
    build_summary,
    execute_capture,
    validate_inputs,
)


class Phase36B3MTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.policy = {
            "required_record_count": 347,
            "required_capture_plan_sha256": "a" * 64,
            "required_route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
            "required_official_domain": "sec.gov",
            "execution": {
                "request_timeout_seconds": 45,
                "maximum_retry_attempts": 2,
                "maximum_requests_per_second": 1,
                "retryable_http_statuses": [429, 500, 502, 503, 504],
                "retry_backoff_seconds": [0, 0],
            },
            "authority": {
                "priority_batch_source_capture": True,
                "controlled_capture_execution": True,
                "capture_ledger_review": True,
                "capture_ledger_certification": False,
                "taxonomy_evidence_normalization": False,
                "production_taxonomy_classification": False,
                "automatic_execution": False,
                "direct_uip_database_writes": False,
            },
        }
        records = []
        for index in range(347):
            series = f"S{index:09d}"
            class_id = f"C{index:09d}"
            security_id = f"US-ETF-T{index:03d}"
            records.append(
                {
                    "sequence": index + 1,
                    "security_id": security_id,
                    "symbol": f"T{index:03d}",
                    "sec_cik": "0001100663",
                    "sec_series_id": series,
                    "sec_class_contract_id": class_id,
                    "expected_identity_markers": [series, class_id, f"T{index:03d}"],
                    "capture_state": "CAPTURE_PENDING",
                    "attempt_count": 0,
                    "route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
                    "official_domain": "sec.gov",
                    "request_url": f"https://www.sec.gov/example?series={series}&class={class_id}",
                    "raw_path": str(self.root / "raw" / security_id / "payload.bin"),
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
                }
            )
        self.plan = {"phase": "3.6b.3k", "plan_record_count": 347, "records": records}
        self.authorization = {
            "phase": "3.6b.3l",
            "authorization_complete": True,
            "capture_execution_authorized": True,
            "automatic_execution_authorized": False,
            "authorized_record_count": 347,
            "authorized_route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
            "capture_plan_sha256": "a" * 64,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_inputs_pass(self) -> None:
        validate_inputs(self.plan, self.authorization, self.policy)

    def test_count_drift_fails_closed(self) -> None:
        plan = deepcopy(self.plan)
        plan["records"].pop()
        with self.assertRaises(ValueError):
            validate_inputs(plan, self.authorization, self.policy)

    def test_duplicate_identity_fails_closed(self) -> None:
        plan = deepcopy(self.plan)
        plan["records"][1]["security_id"] = plan["records"][0]["security_id"]
        with self.assertRaises(ValueError):
            validate_inputs(plan, self.authorization, self.policy)

    def test_duplicate_raw_path_fails_closed(self) -> None:
        plan = deepcopy(self.plan)
        plan["records"][1]["raw_path"] = plan["records"][0]["raw_path"]
        with self.assertRaises(ValueError):
            validate_inputs(plan, self.authorization, self.policy)

    def test_uncertified_route_fails_closed(self) -> None:
        plan = deepcopy(self.plan)
        plan["records"][0]["route_type"] = "ISHARES_SYMBOL_PRODUCT_DISCOVERY"
        with self.assertRaises(ValueError):
            validate_inputs(plan, self.authorization, self.policy)

    def test_missing_user_agent_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            execute_capture(
                self.plan,
                self.authorization,
                self.policy,
                self.root / "ledger.json",
                "invalid-user-agent",
                fetcher=lambda *_: {},
                sleeper=lambda _: None,
            )

    def test_successful_capture_preserves_evidence_and_blocks_downstream(self) -> None:
        def fetcher(url: str, *_args):
            query = url.lower()
            return {"payload": query.encode(), "http_status": 200, "final_url": url, "redirect_chain": [url], "error": None}

        output = self.root / "ledger.json"
        result = execute_capture(
            self.plan,
            self.authorization,
            self.policy,
            output,
            "Tester test@example.com",
            fetcher=fetcher,
            sleeper=lambda _: None,
        )
        self.assertTrue(result["capture_ledger_complete"])
        self.assertEqual(result["capture_state_counts"], {"CAPTURED": 347})
        self.assertFalse(result["taxonomy_evidence_normalization_authorized"])
        first = result["records"][0]
        self.assertRegex(first["payload_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(first["retrieved_at_utc"])
        self.assertEqual(first["attempt_count"], 1)
        self.assertTrue(Path(first["raw_path"]).exists())

    def test_retryable_failure_is_retried_with_bounded_attempts(self) -> None:
        calls = {"count": 0}
        def fetcher(url: str, *_args):
            calls["count"] += 1
            if calls["count"] <= 2:
                return {"payload": b"busy", "http_status": 503, "final_url": url, "redirect_chain": [url], "error": "HTTP_ERROR_503"}
            return {"payload": url.lower().encode(), "http_status": 200, "final_url": url, "redirect_chain": [url], "error": None}

        plan = deepcopy(self.plan)
        for record in plan["records"][1:]:
            record["capture_state"] = "CAPTURED"
            record["attempt_count"] = 1
            record["attempt_history"] = [{"attempt_number": 1}]
        result = execute_capture(plan, self.authorization, self.policy, self.root / "retry.json", "Tester test@example.com", fetcher=fetcher, sleeper=lambda _: None)
        self.assertEqual(result["records"][0]["attempt_count"], 3)
        self.assertEqual(result["records"][0]["capture_state"], "CAPTURED")

    def test_resume_skips_final_records(self) -> None:
        calls = {"count": 0}
        def fetcher(url: str, *_args):
            calls["count"] += 1
            return {"payload": url.lower().encode(), "http_status": 200, "final_url": url, "redirect_chain": [url], "error": None}

        output = self.root / "resume.json"
        first = execute_capture(self.plan, self.authorization, self.policy, output, "Tester test@example.com", fetcher=fetcher, sleeper=lambda _: None)
        first_calls = calls["count"]
        second = execute_capture(self.plan, self.authorization, self.policy, output, "Tester test@example.com", fetcher=fetcher, sleeper=lambda _: None)
        self.assertEqual(calls["count"], first_calls)
        self.assertTrue(second["capture_ledger_complete"])

    def test_summary_hash_and_next_step(self) -> None:
        output = self.root / "summary-source.json"
        document = {
            "records": [{} for _ in range(347)],
            "final_record_count": 347,
            "capture_state_counts": {"CAPTURED": 347},
            "capture_ledger_complete": True,
            "next_required_step": "PRIORITY_BATCH_CAPTURE_LEDGER_REVIEW_AND_CERTIFICATION",
        }
        output.write_text(json.dumps(document), encoding="utf-8")
        summary = build_summary(document, output)
        self.assertRegex(summary["capture_ledger_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(summary["next_required_step"], "PRIORITY_BATCH_CAPTURE_LEDGER_REVIEW_AND_CERTIFICATION")
        self.assertFalse(summary["capture_ledger_certification_authorized"])


if __name__ == "__main__":
    unittest.main()
