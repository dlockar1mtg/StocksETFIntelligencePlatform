from __future__ import annotations

import unittest

from foundation.market.sec_series_class_specific_filing_resolution import (
    build_summary,
    choose_resolution,
    document_names_from_index,
    evaluate_candidate,
    iter_candidate_filings,
    remediation_contract_sha256,
    validate_inputs,
)


class Phase36B3PTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = {
            "required_input_phase": "3.6b.3o",
            "required_pilot_record_count": 5,
            "required_input_review_state": "DOCUMENT_CANDIDATE_UNRESOLVED",
            "pilot_symbols": ["AAXJ", "IAI", "IHI", "IYZ", "XVV"],
        }
        self.records = [
            {
                "security_id": f"US-ETF-{symbol}",
                "symbol": symbol,
                "sec_cik": "0001100663",
                "sec_series_id": f"S{i:09d}",
                "sec_class_contract_id": f"C{i:09d}",
                "review_state": "DOCUMENT_CANDIDATE_UNRESOLVED",
            }
            for i, symbol in enumerate(self.policy["pilot_symbols"], 1)
        ]
        self.remediation = {"phase": "3.6b.3o", "records": self.records}

    def test_valid_inputs_preserve_exact_pilot(self) -> None:
        self.assertEqual(validate_inputs(self.remediation, self.policy), self.records)

    def test_population_drift_fails_closed(self) -> None:
        self.remediation["records"].pop()
        with self.assertRaises(ValueError):
            validate_inputs(self.remediation, self.policy)

    def test_symbol_order_drift_fails_closed(self) -> None:
        self.remediation["records"].reverse()
        with self.assertRaises(ValueError):
            validate_inputs(self.remediation, self.policy)

    def test_candidate_filings_filter_allowed_forms(self) -> None:
        submissions = {"filings": {"recent": {
            "form": ["10-K", "497K", "497"],
            "accessionNumber": ["a", "b", "c"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm"],
            "filingDate": ["1", "2", "3"],
        }}}
        values = iter_candidate_filings(submissions, ["497K", "497"], 10)
        self.assertEqual([v["accession_number"] for v in values], ["b", "c"])

    def test_index_document_filter_excludes_assets(self) -> None:
        index = {"directory": {"item": [{"name": "a.htm"}, {"name": "x.css"}, {"name": "b.txt"}]}}
        self.assertEqual(document_names_from_index(index, 10), ["a.htm", "b.txt"])

    def test_resolution_requires_series_and_class(self) -> None:
        record = self.records[0]
        payload = f"{record['sec_series_id']} {record['sec_class_contract_id']} {record['symbol']}".encode()
        self.assertTrue(evaluate_candidate(record, payload)["product_specific"])

    def test_symbol_without_series_class_is_not_specific(self) -> None:
        record = self.records[0]
        self.assertFalse(evaluate_candidate(record, record["symbol"].encode())["product_specific"])


    def test_blank_identifiers_never_match(self) -> None:
        record = {
            "security_id": "US-ETF-TEST",
            "symbol": "",
            "sec_cik": "",
            "sec_series_id": "",
            "sec_class_contract_id": "",
        }

        result = evaluate_candidate(
            record,
            b"generic filing text",
        )

        self.assertEqual(
            result["identity_marker_count"],
            0,
        )

        self.assertFalse(
            result["product_specific"]
        )

    def test_same_issuer_without_series_and_class_fails_closed(self) -> None:
        record = self.records[0]

        payload = (
            f"{record['sec_cik']} "
            "unrelated series prospectus"
        ).encode()

        result = evaluate_candidate(
            record,
            payload,
        )

        self.assertTrue(
            result["identity_markers"][
                "sec_cik"
            ]
        )

        self.assertFalse(
            result["identity_markers"][
                "sec_series_id"
            ]
        )

        self.assertFalse(
            result["identity_markers"][
                "sec_class_contract_id"
            ]
        )

        self.assertFalse(
            result["product_specific"]
        )

    def test_missing_class_contract_id_fails_closed(self) -> None:
        record = dict(
            self.records[0]
        )

        record[
            "sec_class_contract_id"
        ] = ""

        payload = (
            f"{record['sec_series_id']} "
            f"{record['symbol']} "
            f"{record['sec_cik']}"
        ).encode()

        result = evaluate_candidate(
            record,
            payload,
        )

        self.assertFalse(
            result["identity_markers"][
                "sec_class_contract_id"
            ]
        )

        self.assertFalse(
            result["product_specific"]
        )

    def test_single_matching_document_resolves(self) -> None:
        result = choose_resolution(self.records[0], [{"product_specific": True, "document_name": "a.htm"}])
        self.assertEqual(result["review_state"], "SERIES_CLASS_DOCUMENT_RESOLVED")

    def test_multiple_matching_documents_conflict(self) -> None:
        result = choose_resolution(self.records[0], [{"product_specific": True}, {"product_specific": True}])
        self.assertEqual(result["review_state"], "SERIES_CLASS_DOCUMENT_CONFLICTED")

    def test_summary_blocks_full_recapture(self) -> None:
        summary = build_summary([{"review_state": "SERIES_CLASS_DOCUMENT_RESOLVED"}] * 5)
        self.assertTrue(summary["pilot_complete"])
        self.assertFalse(summary["full_priority_batch_recapture_authorized"])
        self.assertFalse(summary["taxonomy_evidence_normalization_authorized"])

    def test_contract_hash_is_deterministic(self) -> None:
        self.assertEqual(remediation_contract_sha256(self.remediation), remediation_contract_sha256(dict(self.remediation)))


if __name__ == "__main__":
    unittest.main()
