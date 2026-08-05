from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.sec_series_class_route_pilot_reliability_review import (
    analyze_aaxj_gap,
    build_review_ledger,
    canonical_json_bytes,
    marker_presence,
    review_resolved_record,
    sha256_bytes,
    validate_accession_reuse,
    validate_resolution_contract,
)


class Phase36B3QTests(unittest.TestCase):
    def setUp(self) -> None:
        self.symbols = ["AAXJ", "IAI", "IHI", "IYZ", "XVV"]
        self.policy = {
            "required_resolution_ledger_sha256": "",
            "required_input_phase": "3.6b.3p",
            "required_pilot_record_count": 5,
            "pilot_symbols": self.symbols,
            "required_resolved_symbols": ["IAI", "IHI", "IYZ", "XVV"],
            "required_unresolved_symbols": ["AAXJ"],
        }
        self.records = []
        for index, symbol in enumerate(self.symbols, 1):
            self.records.append({
                "security_id": f"US-ETF-{symbol}",
                "symbol": symbol,
                "sec_cik": "0001100663",
                "sec_series_id": f"S{index:09d}",
                "sec_class_contract_id": f"C{index:09d}",
                "review_state": "SERIES_CLASS_DOCUMENT_UNRESOLVED" if symbol == "AAXJ" else "SERIES_CLASS_DOCUMENT_RESOLVED",
                "candidate_document_count": 322 if symbol == "AAXJ" else 1,
                "candidate_documents": [],
            })
        self.ledger = {"phase": "3.6b.3p", "records": self.records}

    def test_contract_validation_locks_exact_bytes_and_population(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_bytes(canonical_json_bytes(self.ledger))
            self.policy["required_resolution_ledger_sha256"] = sha256_bytes(path.read_bytes())
            self.assertEqual(validate_resolution_contract(path, self.ledger, self.policy), self.records)

    def test_contract_hash_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(json.dumps(self.ledger), encoding="utf-8")
            self.policy["required_resolution_ledger_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                validate_resolution_contract(path, self.ledger, self.policy)

    def test_unresolved_aaxj_cannot_be_silently_promoted(self) -> None:
        self.records[0]["review_state"] = "SERIES_CLASS_DOCUMENT_RESOLVED"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_bytes(canonical_json_bytes(self.ledger))
            self.policy["required_resolution_ledger_sha256"] = sha256_bytes(path.read_bytes())
            with self.assertRaises(ValueError):
                validate_resolution_contract(path, self.ledger, self.policy)

    def test_marker_recomputation_requires_all_four_identifiers(self) -> None:
        record = self.records[1]
        payload = f"1100663 {record['sec_series_id']} {record['sec_class_contract_id']} {record['symbol']}".encode()
        self.assertTrue(all(marker_presence(record, payload).values()))

    def test_resolved_review_recomputes_raw_hash(self) -> None:
        record = dict(self.records[1])
        with tempfile.TemporaryDirectory() as directory:
            payload = f"1100663 {record['sec_series_id']} {record['sec_class_contract_id']} {record['symbol']}".encode()
            raw = Path(directory) / "raw.htm"
            raw.write_bytes(payload)
            record.update({
                "accession_number": "0001100663-26-000001",
                "document_name": "fund.htm",
                "document_url": "https://www.sec.gov/fund.htm",
                "document_final_url": "https://www.sec.gov/fund.htm",
                "document_raw_path": "raw.htm",
                "document_payload_sha256": sha256_bytes(payload),
                "form": "497K",
                "filing_date": "2026-01-01",
                "identity_markers": {name: True for name in ["sec_cik", "sec_series_id", "sec_class_contract_id", "symbol"]},
            })
            review = review_resolved_record(record, directory, ["sec_cik", "sec_series_id", "sec_class_contract_id", "symbol"])
            self.assertTrue(review["reliable"])
            self.assertEqual(review["stored_document_sha256"], review["recomputed_document_sha256"])

    def test_missing_raw_document_fails_reliability(self) -> None:
        record = dict(self.records[1], document_raw_path="missing.htm")
        with tempfile.TemporaryDirectory() as directory:
            review = review_resolved_record(record, directory, ["sec_cik", "sec_series_id", "sec_class_contract_id", "symbol"])
            self.assertFalse(review["reliable"])

    def test_accession_reuse_requires_independent_reliability(self) -> None:
        reviews = [
            {"symbol": "IAI", "accession_number": "0001100663-26-000001", "reliable": True},
            {"symbol": "IHI", "accession_number": "0001100663-26-000001", "reliable": False},
        ]
        result = validate_accession_reuse(reviews)
        self.assertTrue(result["incorrect_accession_reuse_detected"])
        self.assertFalse(result["accession_reuse_validation_passed"])

    def test_unique_accessions_pass_reuse_review(self) -> None:
        reviews = [
            {"symbol": "IAI", "accession_number": "0001100663-26-000001", "reliable": True},
            {"symbol": "IHI", "accession_number": "0001100663-26-000002", "reliable": True},
        ]
        self.assertTrue(validate_accession_reuse(reviews)["accession_reuse_validation_passed"])

    def test_aaxj_gap_selects_targeted_historical_remediation(self) -> None:
        gap = analyze_aaxj_gap(self.records[0], 322)
        self.assertEqual(gap["review_state"], "TARGETED_HISTORICAL_REMEDIATION_REQUIRED")
        self.assertTrue(gap["gap_findings"]["older_sec_submission_history_files_required"])
        self.assertFalse(gap["accession_assignment_authorized"])

    def test_aaxj_candidate_floor_is_enforced(self) -> None:
        record = dict(self.records[0], candidate_document_count=321)
        self.assertFalse(analyze_aaxj_gap(record, 322)["candidate_floor_met"])

    def test_review_ledger_blocks_all_downstream_authority(self) -> None:
        resolved = [{"reliable": True}] * 4
        accession = {"accession_reuse_validation_passed": True}
        gap = {"candidate_floor_met": True}
        ledger = build_review_ledger("a" * 64, resolved, accession, gap)
        self.assertTrue(ledger["reliability_review_passed"])
        self.assertFalse(ledger["series_class_route_reliability_certified"])
        self.assertFalse(ledger["full_priority_batch_recapture_authorized"])
        self.assertFalse(ledger["taxonomy_evidence_normalization_authorized"])
        self.assertFalse(ledger["benchmark_publication_authorized"])
        self.assertFalse(ledger["uip_export_authorized"])
        self.assertEqual(ledger["next_required_step"], "TARGETED_AAXJ_HISTORICAL_SEC_REMEDIATION")


if __name__ == "__main__":
    unittest.main()
