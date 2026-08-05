from __future__ import annotations

import unittest

from foundation.market.sec_product_specific_filing_document_route_remediation import (
    build_summary,
    evaluate_document,
    select_recent_filing,
    validate_inputs,
)


class Phase36B3OTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = {
            "required_input_phase": "3.6b.3n",
            "required_record_count": 347,
            "required_failed_review_state": "GENERIC_SHARED_PAYLOAD",
            "required_failed_record_count": 347,
            "pilot_symbols": ["AAXJ", "IAI", "IHI", "IYZ", "XVV"],
        }
        self.review = {
            "phase": "3.6b.3n",
            "records": [
                {"security_id": f"ID-{i}", "review_state": "GENERIC_SHARED_PAYLOAD"}
                for i in range(347)
            ],
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

    def test_valid_inputs_select_exact_pilot(self) -> None:
        pilot = validate_inputs(self.review, self.capture, self.policy)
        self.assertEqual([r["symbol"] for r in pilot], self.policy["pilot_symbols"])

    def test_population_drift_fails_closed(self) -> None:
        self.review["records"].pop()
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
