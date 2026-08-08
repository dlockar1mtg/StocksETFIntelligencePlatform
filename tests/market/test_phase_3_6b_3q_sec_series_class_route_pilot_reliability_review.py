from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.sec_series_class_route_pilot_reliability_review import (
    analyze_unresolved_gap,
    build_review_ledger,
    canonical_json_bytes,
    marker_presence,
    review_resolved_record,
    sha256_bytes,
    structured_series_class_ticker_match,
    validate_accession_reuse,
    validate_resolution_contract,
)


class Phase36B3QTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.symbols = [
            "AAXJ",
            "ACWI",
            "IBTJ",
            "IWN",
            "VLUE",
        ]

        self.policy = {
            "required_resolution_ledger_sha256": "",
            "required_input_phase": "3.6b.3p",
            "required_pilot_record_count": 5,
            "pilot_symbols": (
                self.symbols
            ),
            "required_resolved_symbols": [
                "VLUE",
            ],
            "required_unresolved_symbols": [
                "AAXJ",
                "ACWI",
                "IBTJ",
                "IWN",
            ],
        }

        identity = {
            "AAXJ": (
                "S000022496",
                "C000065072",
            ),
            "ACWI": (
                "S000021461",
                "C000061364",
            ),
            "IBTJ": (
                "S000067564",
                "C000217190",
            ),
            "IWN": (
                "S000004342",
                "C000012072",
            ),
            "VLUE": (
                "S000040205",
                "C000124961",
            ),
        }

        self.records = []

        for symbol in self.symbols:
            series_id, class_id = (
                identity[
                    symbol
                ]
            )

            self.records.append(
                {
                    "security_id": (
                        f"US-ETF-{symbol}"
                    ),
                    "symbol": symbol,
                    "sec_cik": (
                        "0001100663"
                    ),
                    "sec_series_id": (
                        series_id
                    ),
                    "sec_class_contract_id": (
                        class_id
                    ),
                    "review_state": (
                        "SERIES_CLASS_DOCUMENT_RESOLVED"
                        if symbol == "VLUE"
                        else
                        "SERIES_CLASS_DOCUMENT_UNRESOLVED"
                    ),
                    "candidate_document_count": (
                        17
                        if symbol == "VLUE"
                        else 26
                    ),
                    "candidate_documents": [],
                }
            )

        self.ledger = {
            "phase": "3.6b.3p",
            "records": (
                self.records
            ),
        }

    def test_contract_validation_locks_live_population(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "ledger.json"
            )

            path.write_bytes(
                canonical_json_bytes(
                    self.ledger
                )
            )

            self.policy[
                "required_resolution_ledger_sha256"
            ] = sha256_bytes(
                path.read_bytes()
            )

            self.assertEqual(
                validate_resolution_contract(
                    path,
                    self.ledger,
                    self.policy,
                ),
                self.records,
            )

    def test_contract_hash_drift_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "ledger.json"
            )

            path.write_text(
                json.dumps(
                    self.ledger
                ),
                encoding="utf-8",
            )

            self.policy[
                "required_resolution_ledger_sha256"
            ] = "0" * 64

            with self.assertRaises(
                ValueError
            ):
                validate_resolution_contract(
                    path,
                    self.ledger,
                    self.policy,
                )

    def test_unresolved_record_cannot_be_silently_promoted(
        self,
    ) -> None:
        self.records[0][
            "review_state"
        ] = (
            "SERIES_CLASS_DOCUMENT_RESOLVED"
        )

        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "ledger.json"
            )

            path.write_bytes(
                canonical_json_bytes(
                    self.ledger
                )
            )

            self.policy[
                "required_resolution_ledger_sha256"
            ] = sha256_bytes(
                path.read_bytes()
            )

            with self.assertRaises(
                ValueError
            ):
                validate_resolution_contract(
                    path,
                    self.ledger,
                    self.policy,
                )

    def test_vlue_cannot_be_silently_demoted(
        self,
    ) -> None:
        self.records[4][
            "review_state"
        ] = (
            "SERIES_CLASS_DOCUMENT_UNRESOLVED"
        )

        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "ledger.json"
            )

            path.write_bytes(
                canonical_json_bytes(
                    self.ledger
                )
            )

            self.policy[
                "required_resolution_ledger_sha256"
            ] = sha256_bytes(
                path.read_bytes()
            )

            with self.assertRaises(
                ValueError
            ):
                validate_resolution_contract(
                    path,
                    self.ledger,
                    self.policy,
                )

    def test_marker_recomputation_requires_all_identifiers(
        self,
    ) -> None:
        record = self.records[4]

        payload = (
            "1100663 "
            f"{record['sec_series_id']} "
            f"{record['sec_class_contract_id']} "
            f"{record['symbol']}"
        ).encode()

        self.assertTrue(
            all(
                marker_presence(
                    record,
                    payload,
                ).values()
            )
        )

    def test_structured_match_requires_same_series_class_block(
        self,
    ) -> None:
        record = self.records[4]

        payload = (
            "<SERIES>"
            "<SERIES-ID>S000040205"
            "<CLASS-CONTRACT>"
            "<CLASS-CONTRACT-ID>C000124961"
            "<CLASS-CONTRACT-TICKER-SYMBOL>VLUE"
            "</CLASS-CONTRACT>"
            "</SERIES>"
        ).encode()

        result = (
            structured_series_class_ticker_match(
                record,
                payload,
            )
        )

        self.assertTrue(
            result[
                "validated"
            ]
        )

        self.assertEqual(
            result[
                "structured_match_count"
            ],
            1,
        )

    def test_cross_block_markers_do_not_validate(
        self,
    ) -> None:
        record = self.records[4]

        payload = (
            "<SERIES>"
            "<SERIES-ID>S000040205"
            "</SERIES>"
            "<SERIES>"
            "<SERIES-ID>S999999999"
            "<CLASS-CONTRACT>"
            "<CLASS-CONTRACT-ID>C000124961"
            "<CLASS-CONTRACT-TICKER-SYMBOL>VLUE"
            "</CLASS-CONTRACT>"
            "</SERIES>"
        ).encode()

        result = (
            structured_series_class_ticker_match(
                record,
                payload,
            )
        )

        self.assertFalse(
            result[
                "validated"
            ]
        )

    def test_resolved_vlue_review_recomputes_hash_and_structure(
        self,
    ) -> None:
        record = dict(
            self.records[4]
        )

        with tempfile.TemporaryDirectory() as directory:
            payload = (
                "<SERIES>"
                "<SERIES-ID>S000040205"
                "<CLASS-CONTRACT>"
                "<CLASS-CONTRACT-ID>C000124961"
                "<CLASS-CONTRACT-TICKER-SYMBOL>VLUE"
                "</CLASS-CONTRACT>"
                "</SERIES>"
                "1100663"
            ).encode()

            raw = (
                Path(directory)
                / "0001193125-26-330968-index-headers.html"
            )

            raw.write_bytes(
                payload
            )

            record.update(
                {
                    "accession_number": (
                        "0001193125-26-330968"
                    ),
                    "document_name": (
                        "0001193125-26-330968-index-headers.html"
                    ),
                    "document_url": (
                        "https://www.sec.gov/header.htm"
                    ),
                    "document_final_url": (
                        "https://www.sec.gov/header.htm"
                    ),
                    "document_raw_path": (
                        raw.name
                    ),
                    "document_payload_sha256": (
                        sha256_bytes(
                            payload
                        )
                    ),
                    "form": "497",
                    "filing_date": (
                        "2026-08-04"
                    ),
                    "identity_markers": {
                        name: True
                        for name in [
                            "sec_cik",
                            "sec_series_id",
                            "sec_class_contract_id",
                            "symbol",
                        ]
                    },
                }
            )

            review = (
                review_resolved_record(
                    record,
                    directory,
                    [
                        "sec_cik",
                        "sec_series_id",
                        "sec_class_contract_id",
                        "symbol",
                    ],
                )
            )

            self.assertTrue(
                review[
                    "reliable"
                ]
            )

            self.assertEqual(
                review[
                    "structured_association"
                ][
                    "structured_match_count"
                ],
                1,
            )

    def test_non_header_document_fails_structured_resolution(
        self,
    ) -> None:
        record = dict(
            self.records[4]
        )

        with tempfile.TemporaryDirectory() as directory:
            payload = (
                "<SERIES>"
                "S000040205 "
                "<CLASS-CONTRACT>"
                "C000124961 VLUE"
                "</CLASS-CONTRACT>"
                "</SERIES>"
                "1100663"
            ).encode()

            raw = (
                Path(directory)
                / "fund.htm"
            )

            raw.write_bytes(
                payload
            )

            record.update(
                {
                    "accession_number": (
                        "0001193125-26-330968"
                    ),
                    "document_name": (
                        "fund.htm"
                    ),
                    "document_url": "x",
                    "document_final_url": "x",
                    "document_raw_path": (
                        raw.name
                    ),
                    "document_payload_sha256": (
                        sha256_bytes(
                            payload
                        )
                    ),
                    "form": "497",
                    "filing_date": (
                        "2026-08-04"
                    ),
                    "identity_markers": {
                        name: True
                        for name in [
                            "sec_cik",
                            "sec_series_id",
                            "sec_class_contract_id",
                            "symbol",
                        ]
                    },
                }
            )

            review = review_resolved_record(
                record,
                directory,
                [
                    "sec_cik",
                    "sec_series_id",
                    "sec_class_contract_id",
                    "symbol",
                ],
            )

            self.assertFalse(
                review[
                    "reliable"
                ]
            )

    def test_unresolved_gap_requires_no_joint_series_class_candidate(
        self,
    ) -> None:
        record = dict(
            self.records[0]
        )

        record[
            "candidate_documents"
        ] = [
            {
                "identity_markers": {
                    "sec_series_id": (
                        True
                    ),
                    "sec_class_contract_id": (
                        False
                    ),
                }
            }
        ]

        result = (
            analyze_unresolved_gap(
                record
            )
        )

        self.assertTrue(
            result[
                "gap_reliably_characterized"
            ]
        )

        self.assertFalse(
            result[
                "series_and_class_seen_together"
            ]
        )

    def test_joint_series_class_candidate_fails_unresolved_review(
        self,
    ) -> None:
        record = dict(
            self.records[0]
        )

        record[
            "candidate_documents"
        ] = [
            {
                "identity_markers": {
                    "sec_series_id": True,
                    "sec_class_contract_id": True,
                }
            }
        ]

        result = (
            analyze_unresolved_gap(
                record
            )
        )

        self.assertFalse(
            result[
                "gap_reliably_characterized"
            ]
        )

    def test_accession_reuse_requires_independent_reliability(
        self,
    ) -> None:
        reviews = [
            {
                "symbol": "VLUE",
                "accession_number": (
                    "0001100663-26-000001"
                ),
                "reliable": True,
            },
            {
                "symbol": "OTHER",
                "accession_number": (
                    "0001100663-26-000001"
                ),
                "reliable": False,
            },
        ]

        result = (
            validate_accession_reuse(
                reviews
            )
        )

        self.assertTrue(
            result[
                "incorrect_accession_reuse_detected"
            ]
        )

    def test_review_ledger_passes_characterization_but_blocks_route_authority(
        self,
    ) -> None:
        resolved = [
            {
                "reliable": True
            }
        ]

        unresolved = [
            {
                "gap_reliably_characterized": (
                    True
                )
            }
            for _ in range(4)
        ]

        accession = {
            "accession_reuse_validation_passed": (
                True
            )
        }

        ledger = build_review_ledger(
            "a" * 64,
            resolved,
            accession,
            unresolved,
        )

        self.assertTrue(
            ledger[
                "reliability_review_passed"
            ]
        )

        self.assertEqual(
            ledger[
                "resolved_record_count_reliable"
            ],
            1,
        )

        self.assertEqual(
            ledger[
                "unresolved_record_count_reliably_characterized"
            ],
            4,
        )

        self.assertFalse(
            ledger[
                "series_class_route_reliability_certified"
            ]
        )

        self.assertFalse(
            ledger[
                "full_priority_batch_recapture_authorized"
            ]
        )

        self.assertFalse(
            ledger[
                "taxonomy_evidence_normalization_authorized"
            ]
        )

        self.assertEqual(
            ledger[
                "next_required_step"
            ],
            "TARGETED_UNRESOLVED_SERIES_CLASS_ROUTE_REMEDIATION",
        )


if __name__ == "__main__":
    unittest.main()
