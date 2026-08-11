from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_accession_executor import (
    AccessionCentricExecutorError,
    build_unresolved_by_cik,
    evaluate_accession_payload,
    execute_accession_wave,
    validate_population_partition,
)


def identity(
    security_id: str,
    symbol: str,
    cik: str,
    series: str,
    class_id: str,
):
    return {
        "security_id": security_id,
        "symbol": symbol,
        "sec_cik": cik,
        "sec_series_id": series,
        "sec_class_contract_id": class_id,
    }


class AccessionCentricExecutorTests(
    unittest.TestCase
):
    def setUp(self):
        self.a = identity(
            "SEC-A",
            "AAA",
            "0000000001",
            "S000001",
            "C000001",
        )

        self.b = identity(
            "SEC-B",
            "BBB",
            "0000000001",
            "S000002",
            "C000002",
        )

        self.c = identity(
            "SEC-C",
            "CCC",
            "0000000002",
            "S000003",
            "C000003",
        )

        self.all = [
            self.a,
            self.b,
            self.c,
        ]

    def execute(
        self,
        *,
        rows,
        payloads,
        checkpoint,
        raw_root,
        cache_roots=(),
        maximum=10,
        unresolved=None,
        resolved=(),
        conflicted=(),
        remediation=(),
    ):
        calls = []

        def fake_fetcher(
            url,
            user_agent,
            timeout,
        ):
            calls.append(url)

            if url not in payloads:
                raise AssertionError(
                    "Unexpected URL: " + url
                )

            return (
                200,
                url,
                payloads[url],
            )

        result = execute_accession_wave(
            wave_rows=rows,
            all_identities=self.all,
            unresolved_security_ids=(
                unresolved
                if unresolved is not None
                else [
                    "SEC-A",
                    "SEC-B",
                    "SEC-C",
                ]
            ),
            resolved_security_ids=resolved,
            conflicted_security_ids=
                conflicted,
            remediation_security_ids=
                remediation,
            wave_plan_sha256="plan-sha",
            wave_membership_sha256=
                "membership-sha",
            raw_root=raw_root,
            checkpoint_path=checkpoint,
            cache_roots=cache_roots,
            maximum_unique_document_requests=
                maximum,
            maximum_requests_per_second=2.0,
            request_timeout_seconds=30,
            user_agent=(
                "UIP offline-test "
                "test@example.com"
            ),
            network_capture_authorized=True,
            fetcher=fake_fetcher,
            sleeper=lambda _: None,
            enforce_production_counts=False,
        )

        return result, calls

    def test_shared_document_evaluated_against_all_identities_for_cik(
        self,
    ):
        payload = (
            b"S000001 C000001 AAA 0000000001"
        )

        evaluations = (
            evaluate_accession_payload(
                sec_cik="0000000001",
                identities=[
                    self.a,
                    self.b,
                ],
                payload=payload,
            )
        )

        self.assertEqual(
            set(evaluations),
            {
                "SEC-A",
                "SEC-B",
            },
        )

        self.assertTrue(
            evaluations["SEC-A"][
                "product_specific"
            ]
        )

        self.assertFalse(
            evaluations["SEC-B"][
                "product_specific"
            ]
        )

    def test_cross_cik_identity_is_blocked(
        self,
    ):
        with self.assertRaises(
            AccessionCentricExecutorError
        ):
            evaluate_accession_payload(
                sec_cik="0000000001",
                identities=[
                    self.a,
                    self.c,
                ],
                payload=b"anything",
            )

    def test_population_partition_must_be_disjoint(
        self,
    ):
        with self.assertRaises(
            AccessionCentricExecutorError
        ):
            validate_population_partition(
                all_identities=self.all,
                unresolved_security_ids=[
                    "SEC-A",
                    "SEC-B",
                ],
                resolved_security_ids=[
                    "SEC-A",
                ],
                conflicted_security_ids=[],
                remediation_security_ids=[
                    "SEC-C",
                ],
                enforce_production_counts=False,
            )

    def test_population_partition_must_be_exhaustive(
        self,
    ):
        with self.assertRaises(
            AccessionCentricExecutorError
        ):
            validate_population_partition(
                all_identities=self.all,
                unresolved_security_ids=[
                    "SEC-A",
                ],
                resolved_security_ids=[],
                conflicted_security_ids=[],
                remediation_security_ids=[
                    "SEC-C",
                ],
                enforce_production_counts=False,
            )

    def test_unresolved_scope_groups_only_by_own_cik(
        self,
    ):
        identities = (
            validate_population_partition(
                all_identities=self.all,
                unresolved_security_ids=[
                    "SEC-A",
                    "SEC-B",
                    "SEC-C",
                ],
                resolved_security_ids=[],
                conflicted_security_ids=[],
                remediation_security_ids=[],
                enforce_production_counts=False,
            )
        )

        grouped = build_unresolved_by_cik(
            identities,
            [
                "SEC-A",
                "SEC-B",
                "SEC-C",
            ],
        )

        self.assertEqual(
            len(
                grouped[
                    "0000000001"
                ]
            ),
            2,
        )

        self.assertEqual(
            len(
                grouped[
                    "0000000002"
                ]
            ),
            1,
        )

    def test_accession_fetch_occurs_once_for_shared_cik(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            row = {
                "sec_cik":
                    "0000000001",
                "accession_number":
                    "0000000001-26-000001",
                "primary_document":
                    "doc.htm",
                "form":
                    "N-1A",
                "filing_date":
                    "2026-01-01",
            }

            url = (
                "https://www.sec.gov/Archives/"
                "edgar/data/1/"
                "000000000126000001/doc.htm"
            )

            result, calls = self.execute(
                rows=[
                    row,
                    dict(row),
                ],
                payloads={
                    url:
                        b"S000001 C000001 AAA 1"
                },
                checkpoint=(
                    Path(td)
                    / "checkpoint.json"
                ),
                raw_root=(
                    Path(td)
                    / "raw"
                ),
            )

            self.assertEqual(
                len(calls),
                1,
            )

            self.assertEqual(
                result[
                    "wave_accession_document_count"
                ],
                1,
            )

            records = {
                value["security_id"]:
                    value
                for value
                in result[
                    "unresolved_records"
                ]
            }

            self.assertEqual(
                records["SEC-A"][
                    "review_state"
                ],
                "SERIES_CLASS_DOCUMENT_RESOLVED",
            )

            self.assertEqual(
                records["SEC-B"][
                    "review_state"
                ],
                "SERIES_CLASS_DOCUMENT_UNRESOLVED",
            )

    def test_two_matching_documents_preserve_conflict_semantics(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                {
                    "sec_cik":
                        "0000000001",
                    "accession_number":
                        "0000000001-26-000001",
                    "primary_document":
                        "a.htm",
                },
                {
                    "sec_cik":
                        "0000000001",
                    "accession_number":
                        "0000000001-26-000002",
                    "primary_document":
                        "b.htm",
                },
            ]

            urls = [
                (
                    "https://www.sec.gov/Archives/"
                    "edgar/data/1/"
                    "000000000126000001/a.htm"
                ),
                (
                    "https://www.sec.gov/Archives/"
                    "edgar/data/1/"
                    "000000000126000002/b.htm"
                ),
            ]

            result, calls = self.execute(
                rows=rows,
                payloads={
                    urls[0]:
                        b"S000001 C000001 AAA 1",
                    urls[1]:
                        b"S000001 C000001 AAA 1",
                },
                checkpoint=(
                    Path(td)
                    / "checkpoint.json"
                ),
                raw_root=(
                    Path(td)
                    / "raw"
                ),
            )

            records = {
                value["security_id"]:
                    value
                for value
                in result[
                    "unresolved_records"
                ]
            }

            self.assertEqual(
                len(calls),
                2,
            )

            self.assertEqual(
                records["SEC-A"][
                    "review_state"
                ],
                "SERIES_CLASS_DOCUMENT_CONFLICTED",
            )

    def test_request_ceiling_is_checked_before_extra_fetch(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                {
                    "sec_cik":
                        "0000000001",
                    "accession_number":
                        "0000000001-26-000001",
                    "primary_document":
                        "a.htm",
                },
                {
                    "sec_cik":
                        "0000000001",
                    "accession_number":
                        "0000000001-26-000002",
                    "primary_document":
                        "b.htm",
                },
            ]

            calls = []

            def fake_fetcher(
                url,
                user_agent,
                timeout,
            ):
                calls.append(url)

                return (
                    200,
                    url,
                    b"no identity markers",
                )

            with self.assertRaises(
                AccessionCentricExecutorError
            ):
                execute_accession_wave(
                    wave_rows=rows,
                    all_identities=self.all,
                    unresolved_security_ids=[
                        "SEC-A",
                        "SEC-B",
                        "SEC-C",
                    ],
                    resolved_security_ids=[],
                    conflicted_security_ids=[],
                    remediation_security_ids=[],
                    wave_plan_sha256=
                        "plan-sha",
                    wave_membership_sha256=
                        "membership-sha",
                    raw_root=(
                        Path(td)
                        / "raw"
                    ),
                    checkpoint_path=(
                        Path(td)
                        / "checkpoint.json"
                    ),
                    maximum_unique_document_requests=1,
                    maximum_requests_per_second=2,
                    request_timeout_seconds=30,
                    user_agent=(
                        "UIP test "
                        "test@example.com"
                    ),
                    network_capture_authorized=True,
                    fetcher=fake_fetcher,
                    sleeper=lambda _: None,
                    enforce_production_counts=False,
                )

            self.assertEqual(
                len(calls),
                1,
            )

    def test_closed_network_gate_blocks_before_fetch(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            calls = []

            def forbidden(
                url,
                user_agent,
                timeout,
            ):
                calls.append(url)

                raise AssertionError(
                    "fetcher reached"
                )

            with self.assertRaises(
                AccessionCentricExecutorError
            ):
                execute_accession_wave(
                    wave_rows=[
                        {
                            "sec_cik":
                                "0000000001",
                            "accession_number":
                                "0000000001-26-000001",
                            "primary_document":
                                "a.htm",
                        }
                    ],
                    all_identities=self.all,
                    unresolved_security_ids=[
                        "SEC-A",
                        "SEC-B",
                        "SEC-C",
                    ],
                    resolved_security_ids=[],
                    conflicted_security_ids=[],
                    remediation_security_ids=[],
                    wave_plan_sha256=
                        "plan-sha",
                    wave_membership_sha256=
                        "membership-sha",
                    raw_root=(
                        Path(td)
                        / "raw"
                    ),
                    checkpoint_path=(
                        Path(td)
                        / "checkpoint.json"
                    ),
                    maximum_unique_document_requests=1,
                    maximum_requests_per_second=2,
                    request_timeout_seconds=30,
                    user_agent=(
                        "UIP test "
                        "test@example.com"
                    ),
                    network_capture_authorized=False,
                    fetcher=forbidden,
                    sleeper=lambda _: None,
                    enforce_production_counts=False,
                )

            self.assertEqual(
                calls,
                [],
            )

    def test_cached_legacy_document_avoids_fetch(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            cached = (
                root
                / "existing"
                / "sec_taxonomy"
                / "filings"
                / "CIK0000000001"
                / "000000000126000001"
                / "a.htm"
            )

            cached.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            cached.write_bytes(
                b"S000001 C000001 AAA 1"
            )

            result, calls = self.execute(
                rows=[
                    {
                        "sec_cik":
                            "0000000001",
                        "accession_number":
                            "0000000001-26-000001",
                        "primary_document":
                            "a.htm",
                    }
                ],
                payloads={},
                checkpoint=(
                    root
                    / "checkpoint.json"
                ),
                raw_root=(
                    root
                    / "new_raw"
                ),
                cache_roots=[
                    root
                    / "existing"
                ],
            )

            self.assertEqual(
                calls,
                [],
            )

            self.assertTrue(
                result[
                    "accession_records"
                ][0][
                    "cache_reused"
                ]
            )

    def test_checkpoint_resume_does_not_refetch_completed_accession(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            rows = [
                {
                    "sec_cik":
                        "0000000001",
                    "accession_number":
                        "0000000001-26-000001",
                    "primary_document":
                        "a.htm",
                },
                {
                    "sec_cik":
                        "0000000001",
                    "accession_number":
                        "0000000001-26-000002",
                    "primary_document":
                        "b.htm",
                },
            ]

            first_url = (
                "https://www.sec.gov/Archives/"
                "edgar/data/1/"
                "000000000126000001/a.htm"
            )

            second_url = (
                "https://www.sec.gov/Archives/"
                "edgar/data/1/"
                "000000000126000002/b.htm"
            )

            first_calls = []

            def interrupted(
                url,
                user_agent,
                timeout,
            ):
                first_calls.append(url)

                if url == second_url:
                    raise RuntimeError(
                        "SIMULATED_INTERRUPTION"
                    )

                return (
                    200,
                    url,
                    b"S000001 C000001 AAA 1",
                )

            with self.assertRaises(
                RuntimeError
            ):
                execute_accession_wave(
                    wave_rows=rows,
                    all_identities=self.all,
                    unresolved_security_ids=[
                        "SEC-A",
                        "SEC-B",
                        "SEC-C",
                    ],
                    resolved_security_ids=[],
                    conflicted_security_ids=[],
                    remediation_security_ids=[],
                    wave_plan_sha256=
                        "plan-sha",
                    wave_membership_sha256=
                        "membership-sha",
                    raw_root=(
                        root
                        / "raw"
                    ),
                    checkpoint_path=(
                        root
                        / "checkpoint.json"
                    ),
                    maximum_unique_document_requests=10,
                    maximum_requests_per_second=2,
                    request_timeout_seconds=30,
                    user_agent=(
                        "UIP test "
                        "test@example.com"
                    ),
                    network_capture_authorized=True,
                    fetcher=interrupted,
                    sleeper=lambda _: None,
                    enforce_production_counts=False,
                )

            self.assertEqual(
                first_calls,
                [
                    first_url,
                    second_url,
                ],
            )

            second_calls = []

            def resume_fetcher(
                url,
                user_agent,
                timeout,
            ):
                second_calls.append(url)

                return (
                    200,
                    url,
                    b"no match",
                )

            result = execute_accession_wave(
                wave_rows=rows,
                all_identities=self.all,
                unresolved_security_ids=[
                    "SEC-A",
                    "SEC-B",
                    "SEC-C",
                ],
                resolved_security_ids=[],
                conflicted_security_ids=[],
                remediation_security_ids=[],
                wave_plan_sha256=
                    "plan-sha",
                wave_membership_sha256=
                    "membership-sha",
                raw_root=(
                    root
                    / "raw"
                ),
                checkpoint_path=(
                    root
                    / "checkpoint.json"
                ),
                maximum_unique_document_requests=10,
                maximum_requests_per_second=2,
                request_timeout_seconds=30,
                user_agent=(
                    "UIP test "
                    "test@example.com"
                ),
                network_capture_authorized=True,
                fetcher=resume_fetcher,
                sleeper=lambda _: None,
                enforce_production_counts=False,
            )

            self.assertEqual(
                second_calls,
                [
                    second_url,
                ],
            )

            self.assertTrue(
                result[
                    "accession_records"
                ][0][
                    "resume_reused"
                ]
            )

    def test_checkpoint_hash_mismatch_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            checkpoint = (
                root
                / "checkpoint.json"
            )

            checkpoint.write_text(
                json.dumps(
                    {
                        "artifact_id":
                            (
                                "ETF_849_ACCESSION_CENTRIC_"
                                "DOCUMENT_EXECUTION_CHECKPOINT"
                            ),
                        "execution_model":
                            (
                                "FETCH_ACCESSION_ONCE_AND_"
                                "EVALUATE_ALL_UNRESOLVED_"
                                "IDENTITIES_FOR_CIK"
                            ),
                        "wave_plan_sha256":
                            "WRONG",
                        "wave_membership_sha256":
                            "membership-sha",
                        "completed": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                AccessionCentricExecutorError
            ):
                execute_accession_wave(
                    wave_rows=[],
                    all_identities=self.all,
                    unresolved_security_ids=[
                        "SEC-A",
                        "SEC-B",
                        "SEC-C",
                    ],
                    resolved_security_ids=[],
                    conflicted_security_ids=[],
                    remediation_security_ids=[],
                    wave_plan_sha256=
                        "plan-sha",
                    wave_membership_sha256=
                        "membership-sha",
                    raw_root=(
                        root
                        / "raw"
                    ),
                    checkpoint_path=
                        checkpoint,
                    maximum_unique_document_requests=0,
                    maximum_requests_per_second=2,
                    request_timeout_seconds=30,
                    user_agent=(
                        "UIP test "
                        "test@example.com"
                    ),
                    network_capture_authorized=False,
                    fetcher=None,
                    sleeper=lambda _: None,
                    enforce_production_counts=False,
                )

    def test_preserved_populations_receive_zero_evaluations(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            result, calls = self.execute(
                rows=[
                    {
                        "sec_cik":
                            "0000000001",
                        "accession_number":
                            "0000000001-26-000001",
                        "primary_document":
                            "a.htm",
                    }
                ],
                payloads={
                    (
                        "https://www.sec.gov/Archives/"
                        "edgar/data/1/"
                        "000000000126000001/a.htm"
                    ):
                        b"S000001 C000001 AAA 1"
                },
                checkpoint=(
                    Path(td)
                    / "checkpoint.json"
                ),
                raw_root=(
                    Path(td)
                    / "raw"
                ),
                unresolved=[
                    "SEC-A",
                ],
                resolved=[
                    "SEC-B",
                ],
                remediation=[
                    "SEC-C",
                ],
            )

            self.assertEqual(
                len(calls),
                1,
            )

            self.assertEqual(
                result[
                    "unresolved_standard_input_count"
                ],
                1,
            )

            self.assertEqual(
                result[
                    "preserved_resolved_standard_count"
                ],
                1,
            )

            self.assertEqual(
                result[
                    "preserved_remediation_count"
                ],
                1,
            )

            self.assertEqual(
                {
                    value["security_id"]
                    for value
                    in result[
                        "unresolved_records"
                    ]
                },
                {
                    "SEC-A",
                },
            )

    def test_no_taxonomy_or_downstream_actions_are_performed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            result, calls = self.execute(
                rows=[],
                payloads={},
                checkpoint=(
                    Path(td)
                    / "checkpoint.json"
                ),
                raw_root=(
                    Path(td)
                    / "raw"
                ),
            )

            for field in (
                "taxonomy_classification_performed",
                "taxonomy_normalization_performed",
                "ranking_performed",
                "recommendations_performed",
                "allocation_performed",
                "automatic_execution_performed",
                "uip_database_writes_performed",
            ):
                self.assertEqual(
                    result[field],
                    0,
                )

            self.assertEqual(
                calls,
                [],
            )

    def test_production_count_contract_is_fail_closed(
        self,
    ):
        with self.assertRaises(
            AccessionCentricExecutorError
        ):
            validate_population_partition(
                all_identities=self.all,
                unresolved_security_ids=[
                    "SEC-A",
                    "SEC-B",
                    "SEC-C",
                ],
                resolved_security_ids=[],
                conflicted_security_ids=[],
                remediation_security_ids=[],
                enforce_production_counts=True,
            )

    def test_atomic_write_retries_transient_permission_error(
        self,
    ):
        import json
        from unittest.mock import patch

        from foundation.market import (
            authoritative_etf_taxonomy_accession_executor
            as executor_module
        )

        with tempfile.TemporaryDirectory() as td:
            target = (
                Path(td)
                / "checkpoint.json"
            )

            actual_replace = (
                executor_module.os.replace
            )

            attempts = []

            def transient_replace(
                source,
                destination,
            ):
                attempts.append(
                    (
                        str(source),
                        str(destination),
                    )
                )

                if len(attempts) < 3:
                    raise PermissionError(
                        "simulated transient lock"
                    )

                return actual_replace(
                    source,
                    destination,
                )

            with (
                patch.object(
                    executor_module.os,
                    "replace",
                    side_effect=
                        transient_replace,
                ),
                patch.object(
                    executor_module.time,
                    "sleep",
                    return_value=None,
                ) as mocked_sleep,
            ):
                executor_module._atomic_write_json(
                    target,
                    {
                        "ok": True,
                    },
                )

            self.assertEqual(
                len(attempts),
                3,
            )

            self.assertEqual(
                mocked_sleep.call_count,
                2,
            )

            self.assertEqual(
                json.loads(
                    target.read_text(
                        encoding="utf-8"
                    )
                ),
                {
                    "ok": True,
                },
            )

            self.assertFalse(
                target.with_suffix(
                    ".json.tmp"
                ).exists()
            )

    def test_atomic_write_fails_closed_after_persistent_permission_error(
        self,
    ):
        from unittest.mock import patch

        from foundation.market import (
            authoritative_etf_taxonomy_accession_executor
            as executor_module
        )

        with tempfile.TemporaryDirectory() as td:
            target = (
                Path(td)
                / "checkpoint.json"
            )

            with (
                patch.object(
                    executor_module.os,
                    "replace",
                    side_effect=
                        PermissionError(
                            "persistent simulated lock"
                        ),
                ) as mocked_replace,
                patch.object(
                    executor_module.time,
                    "sleep",
                    return_value=None,
                ) as mocked_sleep,
            ):
                with self.assertRaises(
                    PermissionError
                ):
                    executor_module._atomic_write_json(
                        target,
                        {
                            "ok": False,
                        },
                    )

            self.assertEqual(
                mocked_replace.call_count,
                8,
            )

            self.assertEqual(
                mocked_sleep.call_count,
                7,
            )


    def test_checkpoint_persists_evaluations_and_final_security_outcomes(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            checkpoint = (
                root
                / "checkpoint.json"
            )

            row = {
                "sec_cik":
                    "0000000001",
                "accession_number":
                    "0000000001-26-000001",
                "primary_document":
                    "a.htm",
            }

            result, calls = self.execute(
                rows=[
                    row,
                ],
                payloads={
                    (
                        "https://www.sec.gov/Archives/"
                        "edgar/data/1/"
                        "000000000126000001/a.htm"
                    ):
                        b"S000001 C000001 AAA 1"
                },
                checkpoint=checkpoint,
                raw_root=(
                    root
                    / "raw"
                ),
            )

            self.assertEqual(
                len(calls),
                1,
            )

            value = json.loads(
                checkpoint.read_text(
                    encoding="utf-8"
                )
            )

            completed = value[
                "completed"
            ]

            self.assertEqual(
                len(completed),
                1,
            )

            entry = next(
                iter(
                    completed.values()
                )
            )

            self.assertIn(
                "evaluations",
                entry,
            )

            self.assertIn(
                "evaluations_sha256",
                entry,
            )

            self.assertEqual(
                set(
                    entry[
                        "evaluations"
                    ]
                ),
                {
                    "SEC-A",
                    "SEC-B",
                },
            )

            self.assertEqual(
                entry[
                    "evaluated_identity_count"
                ],
                2,
            )

            self.assertIn(
                "matching_security_ids",
                entry,
            )

            self.assertEqual(
                set(
                    value[
                        "security_outcomes"
                    ]
                ),
                {
                    "SEC-A",
                    "SEC-B",
                    "SEC-C",
                },
            )

            self.assertIn(
                "security_outcomes_sha256",
                value,
            )

            returned = {
                item["security_id"]:
                    item
                for item
                in result[
                    "unresolved_records"
                ]
            }

            self.assertEqual(
                value[
                    "security_outcomes"
                ],
                returned,
            )

    def test_checkpoint_resume_reuses_persisted_evaluations(
        self,
    ):
        from unittest.mock import patch

        from foundation.market import (
            authoritative_etf_taxonomy_accession_executor
            as executor_module
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            checkpoint = (
                root
                / "checkpoint.json"
            )

            row = {
                "sec_cik":
                    "0000000001",
                "accession_number":
                    "0000000001-26-000001",
                "primary_document":
                    "a.htm",
            }

            url = (
                "https://www.sec.gov/Archives/"
                "edgar/data/1/"
                "000000000126000001/a.htm"
            )

            first_result, first_calls = (
                self.execute(
                    rows=[
                        row,
                    ],
                    payloads={
                        url:
                            b"S000001 C000001 AAA 1"
                    },
                    checkpoint=
                        checkpoint,
                    raw_root=(
                        root
                        / "raw"
                    ),
                )
            )

            self.assertEqual(
                first_calls,
                [
                    url,
                ],
            )

            def forbidden_evaluation(
                *args,
                **kwargs,
            ):
                raise AssertionError(
                    "persisted evaluation should be reused"
                )

            second_calls = []

            def forbidden_fetch(
                url,
                user_agent,
                timeout,
            ):
                second_calls.append(
                    url
                )

                raise AssertionError(
                    "completed accession must not refetch"
                )

            with patch.object(
                executor_module,
                "evaluate_accession_payload",
                side_effect=
                    forbidden_evaluation,
            ):
                second_result = (
                    execute_accession_wave(
                        wave_rows=[
                            row,
                        ],
                        all_identities=
                            self.all,
                        unresolved_security_ids=[
                            "SEC-A",
                            "SEC-B",
                            "SEC-C",
                        ],
                        resolved_security_ids=[],
                        conflicted_security_ids=[],
                        remediation_security_ids=[],
                        wave_plan_sha256=
                            "plan-sha",
                        wave_membership_sha256=
                            "membership-sha",
                        raw_root=(
                            root
                            / "raw"
                        ),
                        checkpoint_path=
                            checkpoint,
                        maximum_unique_document_requests=
                            10,
                        maximum_requests_per_second=
                            2,
                        request_timeout_seconds=
                            30,
                        user_agent=(
                            "UIP test "
                            "test@example.com"
                        ),
                        network_capture_authorized=
                            True,
                        fetcher=
                            forbidden_fetch,
                        sleeper=
                            lambda _: None,
                        enforce_production_counts=
                            False,
                    )
                )

            self.assertEqual(
                second_calls,
                [],
            )

            self.assertTrue(
                second_result[
                    "accession_records"
                ][0][
                    "resume_reused"
                ]
            )

            first_records = {
                item["security_id"]:
                    item
                for item
                in first_result[
                    "unresolved_records"
                ]
            }

            second_records = {
                item["security_id"]:
                    item
                for item
                in second_result[
                    "unresolved_records"
                ]
            }

            self.assertEqual(
                second_records,
                first_records,
            )

    def test_checkpoint_evaluation_tamper_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            checkpoint = (
                root
                / "checkpoint.json"
            )

            row = {
                "sec_cik":
                    "0000000001",
                "accession_number":
                    "0000000001-26-000001",
                "primary_document":
                    "a.htm",
            }

            url = (
                "https://www.sec.gov/Archives/"
                "edgar/data/1/"
                "000000000126000001/a.htm"
            )

            self.execute(
                rows=[
                    row,
                ],
                payloads={
                    url:
                        b"S000001 C000001 AAA 1"
                },
                checkpoint=
                    checkpoint,
                raw_root=(
                    root
                    / "raw"
                ),
            )

            value = json.loads(
                checkpoint.read_text(
                    encoding="utf-8"
                )
            )

            value[
                "completed"
            ][url][
                "evaluations"
            ][
                "SEC-A"
            ][
                "product_specific"
            ] = False

            checkpoint.write_text(
                json.dumps(
                    value,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                AccessionCentricExecutorError,
                "CHECKPOINT_EVALUATIONS_HASH_MISMATCH",
            ):
                execute_accession_wave(
                    wave_rows=[
                        row,
                    ],
                    all_identities=
                        self.all,
                    unresolved_security_ids=[
                        "SEC-A",
                        "SEC-B",
                        "SEC-C",
                    ],
                    resolved_security_ids=[],
                    conflicted_security_ids=[],
                    remediation_security_ids=[],
                    wave_plan_sha256=
                        "plan-sha",
                    wave_membership_sha256=
                        "membership-sha",
                    raw_root=(
                        root
                        / "raw"
                    ),
                    checkpoint_path=
                        checkpoint,
                    maximum_unique_document_requests=
                        0,
                    maximum_requests_per_second=
                        2,
                    request_timeout_seconds=
                        30,
                    user_agent=(
                        "UIP test "
                        "test@example.com"
                    ),
                    network_capture_authorized=
                        False,
                    fetcher=None,
                    sleeper=
                        lambda _: None,
                    enforce_production_counts=
                        False,
                )

    def test_checkpoint_final_outcome_tamper_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            checkpoint = (
                root
                / "checkpoint.json"
            )

            result, calls = self.execute(
                rows=[],
                payloads={},
                checkpoint=
                    checkpoint,
                raw_root=(
                    root
                    / "raw"
                ),
            )

            self.assertEqual(
                calls,
                [],
            )

            value = json.loads(
                checkpoint.read_text(
                    encoding="utf-8"
                )
            )

            value[
                "security_outcomes"
            ][
                "SEC-A"
            ][
                "review_state"
            ] = "TAMPERED"

            checkpoint.write_text(
                json.dumps(
                    value,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                AccessionCentricExecutorError,
                "CHECKPOINT_SECURITY_OUTCOMES_HASH_MISMATCH",
            ):
                execute_accession_wave(
                    wave_rows=[],
                    all_identities=
                        self.all,
                    unresolved_security_ids=[
                        "SEC-A",
                        "SEC-B",
                        "SEC-C",
                    ],
                    resolved_security_ids=[],
                    conflicted_security_ids=[],
                    remediation_security_ids=[],
                    wave_plan_sha256=
                        "plan-sha",
                    wave_membership_sha256=
                        "membership-sha",
                    raw_root=(
                        root
                        / "raw"
                    ),
                    checkpoint_path=
                        checkpoint,
                    maximum_unique_document_requests=
                        0,
                    maximum_requests_per_second=
                        2,
                    request_timeout_seconds=
                        30,
                    user_agent=(
                        "UIP test "
                        "test@example.com"
                    ),
                    network_capture_authorized=
                        False,
                    fetcher=None,
                    sleeper=
                        lambda _: None,
                    enforce_production_counts=
                        False,
                )



if __name__ == "__main__":
    unittest.main()
