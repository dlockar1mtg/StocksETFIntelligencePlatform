from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.sec_product_specific_filing_document_route_remediation import (
    build_summary,
    evaluate_document,
    validate_corrected_pilot_manifest,
    iter_recent_filings,
    load_json,
    review_ledger_contract_sha256,
    select_recent_filing,
    validate_inputs,
)


class Phase36B3OTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review = {
            "phase": "3.6b.3n",
            "records": [
                {"security_id": f"ID-{i}", "review_state": "GENERIC_SHARED_PAYLOAD"}
                for i in range(347)
            ],
        }
        self.policy = {
            "required_input_phase": "3.6b.3n",
            "required_record_count": 347,
            "required_failed_review_state": "GENERIC_SHARED_PAYLOAD",
            "required_failed_record_count": 347,
            "required_review_ledger_sha256": review_ledger_contract_sha256(self.review),
            "pilot_symbols": ["AAXJ", "IAI", "IHI", "IYZ", "XVV"],
        }
        self.capture = {
            "records": [
                {
                    "security_id": f"US-ETF-{symbol}",
                    "symbol": symbol,
                    "sec_cik": "0001100663",
                    "sec_series_id": f"S{i:09d}",
                    "sec_class_contract_id": f"C{i:09d}",
                }
                for i, symbol in enumerate(["AAXJ", "IAI", "IHI", "IYZ", "XVV"], 1)
            ]
        }

    def test_load_json_accepts_utf8_bom(self) -> None:
        payload = {
            "artifact_id": "BOM_TEST",
            "record_count": 1,
        }

        encoded = (
            b"\xef\xbb\xbf"
            + json.dumps(payload).encode("utf-8")
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bom.json"
            path.write_bytes(encoded)

            loaded = load_json(path)

        self.assertEqual(
            loaded,
            payload,
        )

    def test_load_json_accepts_plain_utf8(self) -> None:
        payload = {
            "artifact_id": "PLAIN_UTF8_TEST",
            "record_count": 1,
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plain.json"
            path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            loaded = load_json(path)

        self.assertEqual(
            loaded,
            payload,
        )

    def test_valid_inputs_select_exact_pilot(self) -> None:
        pilot = validate_inputs(self.review, self.capture, self.policy)
        self.assertEqual([r["symbol"] for r in pilot], self.policy["pilot_symbols"])

    def test_population_drift_fails_closed(self) -> None:
        self.review["records"].pop()
        with self.assertRaises(ValueError):
            validate_inputs(self.review, self.capture, self.policy)

    def test_review_contract_hash_ignores_storage_newline_style(self) -> None:
        logical_hash = review_ledger_contract_sha256(self.review)
        self.assertEqual(logical_hash, self.policy["required_review_ledger_sha256"])

    def test_review_contract_hash_drift_fails_closed(self) -> None:
        self.review["records"][0]["review_state"] = "PRODUCT_SPECIFIC_EVIDENCE"
        with self.assertRaises(ValueError):
            validate_inputs(self.review, self.capture, self.policy)

    def test_missing_pilot_symbol_fails_closed(self) -> None:
        self.capture["records"].pop()
        with self.assertRaises(ValueError):
            validate_inputs(self.review, self.capture, self.policy)

    def test_select_recent_filing_uses_allowed_form(self) -> None:
        submissions = {"filings": {"recent": {
            "form": ["10-K", "497K"],
            "accessionNumber": ["a", "b"],
            "primaryDocument": ["a.htm", "b.htm"],
            "filingDate": ["2026-01-01", "2026-02-01"],
        }}}
        filing = select_recent_filing(submissions, ["497K"], 10)
        self.assertEqual(filing["accession_number"], "b")

    def test_missing_allowed_filing_is_unresolved(self) -> None:
        self.assertIsNone(select_recent_filing({"filings": {"recent": {}}}, ["497"], 10))


    def test_corrected_manifest_contract_accepts_five_distinct_products(self) -> None:
        records = []

        for index in range(5):
            records.append(
                {
                    "security_id": f"US-ETF-T{index}",
                    "symbol": f"T{index}",
                    "sec_cik": "0001100663",
                    "sec_series_id": f"S00000000{index}",
                    "sec_class_contract_id": f"C00000000{index}",
                    "remediation_queue": "FILING_ROUTE_DISCOVERY_REQUIRED",
                    "maximum_candidate_documents": 5,
                    "prior_candidate_route_reuse_authorized": False,
                    "network_execution_authorized": False,
                }
            )

        manifest = {
            "artifact_id": "CORRECTED_SEC_ROUTE_DISCOVERY_PILOT_MANIFEST",
            "pilot_record_count": 5,
            "maximum_candidate_documents_per_security": 5,
            "maximum_total_sec_requests": 30,
            "maximum_requests_per_second": 1,
            "network_execution_authorized": False,
            "records": records,
        }

        validated = (
            validate_corrected_pilot_manifest(
                manifest
            )
        )

        self.assertEqual(
            len(validated),
            5,
        )

    def test_corrected_manifest_does_not_self_authorize_network(self) -> None:
        manifest = {
            "artifact_id": "CORRECTED_SEC_ROUTE_DISCOVERY_PILOT_MANIFEST",
            "pilot_record_count": 5,
            "maximum_candidate_documents_per_security": 5,
            "maximum_total_sec_requests": 30,
            "maximum_requests_per_second": 1,
            "network_execution_authorized": True,
            "records": [],
        }

        with self.assertRaises(ValueError):
            validate_corrected_pilot_manifest(
                manifest
            )

    def test_corrected_manifest_requires_unique_series_and_class_identity(self) -> None:
        records = []

        for index in range(5):
            records.append(
                {
                    "security_id": f"US-ETF-T{index}",
                    "symbol": f"T{index}",
                    "sec_cik": "0001100663",
                    "sec_series_id": "SAME-SERIES",
                    "sec_class_contract_id": f"C00000000{index}",
                    "remediation_queue": "FILING_ROUTE_DISCOVERY_REQUIRED",
                    "maximum_candidate_documents": 5,
                    "prior_candidate_route_reuse_authorized": False,
                    "network_execution_authorized": False,
                }
            )

        manifest = {
            "artifact_id": "CORRECTED_SEC_ROUTE_DISCOVERY_PILOT_MANIFEST",
            "pilot_record_count": 5,
            "maximum_candidate_documents_per_security": 5,
            "maximum_total_sec_requests": 30,
            "maximum_requests_per_second": 1,
            "network_execution_authorized": False,
            "records": records,
        }

        with self.assertRaises(ValueError):
            validate_corrected_pilot_manifest(
                manifest
            )


    def test_corrected_manifest_execution_has_absolute_request_ceiling(self) -> None:
        from pathlib import Path

        repository_root = (
            Path(__file__).resolve().parents[2]
        )

        runner_source = (
            repository_root
            / "scripts"
            / "run_phase_3_6b_3o_sec_product_specific_filing_document_route_remediation.py"
        ).read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "corrected_pilot_mode = bool(",
            runner_source,
        )

        self.assertIn(
            "effective_retry_attempts = (",
            runner_source,
        )

        self.assertIn(
            "0\n        if corrected_pilot_mode",
            runner_source,
        )

        self.assertIn(
            "request_interval_seconds = (",
            runner_source,
        )

        self.assertIn(
            "time.sleep(\n                request_interval_seconds",
            runner_source,
        )

    def test_legacy_execution_retains_policy_retry_contract(self) -> None:
        from pathlib import Path

        repository_root = (
            Path(__file__).resolve().parents[2]
        )

        runner_source = (
            repository_root
            / "scripts"
            / "run_phase_3_6b_3o_sec_product_specific_filing_document_route_remediation.py"
        ).read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            'execution[\n                "maximum_retry_attempts"\n            ]',
            runner_source,
        )


    def test_runner_contract_contains_candidate_document_ceiling(self) -> None:
        from pathlib import Path

        repository_root = (
            Path(__file__).resolve().parents[2]
        )

        runner_source = (
            repository_root
            / "scripts"
            / "run_phase_3_6b_3o_sec_product_specific_filing_document_route_remediation.py"
        ).read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "maximum_candidate_documents_per_security",
            runner_source,
        )

        self.assertIn(
            '"maximum_recent_filings_scanned"',
            runner_source,
        )

        self.assertIn(
            "min(",
            runner_source,
        )


    def test_recent_filings_are_candidates_only(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": [
                        "497",
                        "497K",
                        "10-K",
                    ],
                    "accessionNumber": [
                        "a",
                        "b",
                        "c",
                    ],
                    "primaryDocument": [
                        "a.htm",
                        "b.htm",
                        "c.htm",
                    ],
                    "filingDate": [
                        "2026-08-03",
                        "2026-08-02",
                        "2026-08-01",
                    ],
                }
            }
        }

        candidates = iter_recent_filings(
            submissions,
            ["497", "497K"],
            10,
        )

        self.assertEqual(
            [
                value["accession_number"]
                for value in candidates
            ],
            ["a", "b"],
        )

    def test_blank_identifiers_never_match(self) -> None:
        record = {
            "security_id": "US-ETF-TEST",
            "symbol": "",
            "sec_cik": "",
            "sec_series_id": "",
            "sec_class_contract_id": "",
        }

        result = evaluate_document(
            record,
            b"generic filing text",
            "0001",
            "document.htm",
        )

        self.assertEqual(
            result["identity_marker_count"],
            0,
        )

        self.assertFalse(
            result["product_specific"]
        )

    def test_same_issuer_unrelated_filing_fails_closed(self) -> None:
        record = self.capture["records"][0]

        payload = (
            f"{record['sec_cik']} "
            "unrelated BlackRock fund prospectus"
        ).encode()

        result = evaluate_document(
            record,
            payload,
            "0001193125-26-330968",
            "d55058d497.htm",
        )

        self.assertTrue(
            result["identity_markers"]["cik"]
        )

        self.assertFalse(
            result["identity_markers"][
                "series_id"
            ]
        )

        self.assertFalse(
            result["identity_markers"][
                "class_contract_id"
            ]
        )

        self.assertFalse(
            result["product_specific"]
        )

        self.assertEqual(
            result["review_state"],
            "DOCUMENT_CANDIDATE_UNRESOLVED",
        )

    def test_missing_class_contract_id_fails_closed(self) -> None:
        record = dict(
            self.capture["records"][0]
        )

        record[
            "sec_class_contract_id"
        ] = ""

        payload = (
            f"{record['sec_cik']} "
            f"{record['sec_series_id']} "
            f"{record['symbol']}"
        ).encode()

        result = evaluate_document(
            record,
            payload,
            "0001",
            "document.htm",
        )

        self.assertFalse(
            result["identity_markers"][
                "class_contract_id"
            ]
        )

        self.assertFalse(
            result["product_specific"]
        )

    def test_product_specific_document_requires_series_and_class(self) -> None:
        record = self.capture["records"][0]
        payload = f"{record['sec_cik']} {record['sec_series_id']} {record['sec_class_contract_id']} {record['symbol']}".encode()
        result = evaluate_document(record, payload, "0001-01-01", "doc.htm")
        self.assertEqual(result["review_state"], "PRODUCT_SPECIFIC_DOCUMENT_RESOLVED")

    def test_generic_document_is_not_resolved(self) -> None:
        result = evaluate_document(self.capture["records"][0], b"generic sec page", "0001", "doc.htm")
        self.assertFalse(result["product_specific"])

    def test_http_success_alone_cannot_resolve(self) -> None:
        result = evaluate_document(self.capture["records"][0], b"200 OK", "0001", "doc.htm")
        self.assertEqual(result["review_state"], "DOCUMENT_CANDIDATE_UNRESOLVED")

    def test_summary_blocks_full_recapture(self) -> None:
        summary = build_summary([{"review_state": "PRODUCT_SPECIFIC_DOCUMENT_RESOLVED"}] * 5)
        self.assertFalse(summary["full_priority_batch_recapture_authorized"])
        self.assertFalse(summary["taxonomy_evidence_normalization_authorized"])

    def test_summary_requires_five_final_records(self) -> None:
        summary = build_summary([{"review_state": "PRODUCT_SPECIFIC_DOCUMENT_RESOLVED"}] * 4)
        self.assertFalse(summary["pilot_complete"])


if __name__ == "__main__":
    unittest.main()
