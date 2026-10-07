from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_historical_metadata_capture import (
    HistoricalMetadataCaptureError,
    build_offline_plan,
    capture_historical_metadata,
    load_json,
    sha256_path,
)


ROOT = Path(
    __file__
).resolve().parents[2]

RUN_ROOT = (
    ROOT
    / "artifacts"
    / "analysis"
    / "phase_3_model_taxonomy_production"
    / "2026-08-09"
    / "live_sec_capture"
    / "standard-sec-20260809T182408Z"
)

PLAN_PATH = (
    RUN_ROOT
    / "unresolved_standard_historical_metadata_plan.json"
)

AUTHORIZATION_PATH = (
    ROOT
    / "config"
    / "market"
    / "authoritative_etf_taxonomy_historical_metadata_capture_authorization.json"
)

EXPECTED_PLAN_SHA = (
    "6a6c9eb77cc6fe6c4e07ddb26c4f0026"
    "e24e7ccf917c4a7a9b09cd73884d3dc3"
)


def fake_shard_payload():
    return json.dumps(
        {
            "accessionNumber": [
                "0000000000-20-000001",
                "0000000000-20-000002",
                "0000000000-20-000003",
            ],
            "filingDate": [
                "2020-01-01",
                "2020-01-02",
                "2020-01-03",
            ],
            "form": [
                "497",
                "N-1A",
                "10-K",
            ],
            "primaryDocument": [
                "a.htm",
                "b.htm",
                "c.htm",
            ],
        }
    ).encode(
        "utf-8"
    )


class HistoricalMetadataCaptureTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ):
        if not PLAN_PATH.exists():  # gitignored local artifact (artifacts/), present only on the governed local run
            raise unittest.SkipTest(f"local governed artifact not present: {PLAN_PATH.name}")
        cls.plan = load_json(
            PLAN_PATH
        )

        cls.authorization = load_json(
            AUTHORIZATION_PATH
        )

    def test_plan_sha_is_frozen(
        self,
    ):
        self.assertEqual(
            sha256_path(
                PLAN_PATH
            ),
            EXPECTED_PLAN_SHA,
        )

    def test_offline_plan_is_exact_102_shards(
        self,
    ):
        result = build_offline_plan(
            self.plan,
            self.authorization,
            plan_sha256=
                EXPECTED_PLAN_SHA,
        )

        self.assertEqual(
            result[
                "historical_target_etf_count"
            ],
            849,
        )

        self.assertEqual(
            result[
                "historical_submission_shard_count"
            ],
            102,
        )

        self.assertEqual(
            result[
                "maximum_unique_sec_requests"
            ],
            102,
        )

        self.assertEqual(
            result[
                "network_requests_performed"
            ],
            0,
        )

        self.assertFalse(
            result[
                "filing_document_requests_authorized"
            ]
        )

    def test_plan_cannot_self_authorize_capture(
        self,
    ):
        plan = copy.deepcopy(
            self.plan
        )

        plan[
            "historical_shard_capture_authorized"
        ] = True

        with self.assertRaises(
            HistoricalMetadataCaptureError
        ):
            build_offline_plan(
                plan,
                self.authorization,
                plan_sha256=
                    EXPECTED_PLAN_SHA,
            )

    def test_document_capture_authority_must_remain_false(
        self,
    ):
        authorization = copy.deepcopy(
            self.authorization
        )

        authorization[
            "historical_filing_document_capture_authorized"
        ] = True

        with self.assertRaises(
            HistoricalMetadataCaptureError
        ):
            build_offline_plan(
                self.plan,
                authorization,
                plan_sha256=
                    EXPECTED_PLAN_SHA,
            )

    def test_full_102_shard_capture_uses_injected_transport(
        self,
    ):
        calls = []

        payload = fake_shard_payload()

        def fake_fetcher(
            url,
            user_agent,
            timeout,
        ):
            calls.append(
                url
            )

            return (
                200,
                url,
                payload,
            )

        with tempfile.TemporaryDirectory() as temp:
            checkpoint = (
                Path(temp)
                / "checkpoint.json"
            )

            result = capture_historical_metadata(
                self.plan,
                self.authorization,
                plan_sha256=
                    EXPECTED_PLAN_SHA,
                raw_root=
                    temp,
                checkpoint_path=
                    checkpoint,
                user_agent=
                    "UIP research contact@example.com",
                fetcher=
                    fake_fetcher,
                sleeper=lambda _: None,
            )

            self.assertEqual(
                len(
                    calls
                ),
                102,
            )

            self.assertEqual(
                len(
                    set(
                        calls
                    )
                ),
                102,
            )

            self.assertEqual(
                result[
                    "captured_shard_count"
                ],
                102,
            )

            self.assertEqual(
                result[
                    "current_run_sec_requests_performed"
                ],
                102,
            )

            self.assertEqual(
                result[
                    "historical_filing_metadata_count"
                ],
                306,
            )

            self.assertEqual(
                result[
                    "allowed_form_filing_metadata_count"
                ],
                204,
            )

            self.assertEqual(
                result[
                    "filing_document_requests_performed"
                ],
                0,
            )

            self.assertTrue(
                checkpoint.is_file()
            )

    def test_second_execution_reuses_checkpoint_with_zero_requests(
        self,
    ):
        first_calls = []

        payload = fake_shard_payload()

        def first_fetcher(
            url,
            user_agent,
            timeout,
        ):
            first_calls.append(
                url
            )

            return (
                200,
                url,
                payload,
            )

        def forbidden_fetcher(
            url,
            user_agent,
            timeout,
        ):
            raise AssertionError(
                "Resume-safe execution must not refetch completed shard."
            )

        with tempfile.TemporaryDirectory() as temp:
            checkpoint = (
                Path(temp)
                / "checkpoint.json"
            )

            first = capture_historical_metadata(
                self.plan,
                self.authorization,
                plan_sha256=
                    EXPECTED_PLAN_SHA,
                raw_root=
                    temp,
                checkpoint_path=
                    checkpoint,
                user_agent=
                    "UIP research contact@example.com",
                fetcher=
                    first_fetcher,
                sleeper=lambda _: None,
            )

            second = capture_historical_metadata(
                self.plan,
                self.authorization,
                plan_sha256=
                    EXPECTED_PLAN_SHA,
                raw_root=
                    temp,
                checkpoint_path=
                    checkpoint,
                user_agent=
                    "UIP research contact@example.com",
                fetcher=
                    forbidden_fetcher,
                sleeper=lambda _: None,
            )

            self.assertEqual(
                len(
                    first_calls
                ),
                102,
            )

            self.assertEqual(
                first[
                    "total_completed_shards"
                ],
                102,
            )

            self.assertEqual(
                second[
                    "current_run_sec_requests_performed"
                ],
                0,
            )

            self.assertEqual(
                second[
                    "total_completed_shards"
                ],
                102,
            )

            self.assertTrue(
                all(
                    record[
                        "resume_reused"
                    ]
                    for record
                    in second[
                        "records"
                    ]
                )
            )

    def test_interrupted_execution_persists_completed_checkpoint(
        self,
    ):
        payload = fake_shard_payload()

        calls = []

        def failing_fetcher(
            url,
            user_agent,
            timeout,
        ):
            calls.append(
                url
            )

            if len(
                calls
            ) == 4:
                raise RuntimeError(
                    "synthetic transport interruption"
                )

            return (
                200,
                url,
                payload,
            )

        with tempfile.TemporaryDirectory() as temp:
            checkpoint = (
                Path(temp)
                / "checkpoint.json"
            )

            with self.assertRaises(
                RuntimeError
            ):
                capture_historical_metadata(
                    self.plan,
                    self.authorization,
                    plan_sha256=
                        EXPECTED_PLAN_SHA,
                    raw_root=
                        temp,
                    checkpoint_path=
                        checkpoint,
                    user_agent=
                        "UIP research contact@example.com",
                    fetcher=
                        failing_fetcher,
                    sleeper=lambda _: None,
                )

            saved = json.loads(
                checkpoint.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                len(
                    saved[
                        "completed"
                    ]
                ),
                3,
            )

    def test_authorization_plan_binding_fails_closed(
        self,
    ):
        authorization = copy.deepcopy(
            self.authorization
        )

        authorization[
            "historical_plan_sha256"
        ] = "0" * 64

        with self.assertRaises(
            HistoricalMetadataCaptureError
        ):
            build_offline_plan(
                self.plan,
                authorization,
                plan_sha256=
                    EXPECTED_PLAN_SHA,
            )


if __name__ == "__main__":
    unittest.main()
