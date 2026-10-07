from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_sec_capture_launch import (
    ProductionSECCaptureLaunchError,
    build_launch_plan,
    execute_live,
    load_json,
)


ROOT = Path(__file__).resolve().parents[2]

CONTRACT_PATH = (
    ROOT
    / "artifacts"
    / "analysis"
    / "phase_3_model_taxonomy_production"
    / "2026-08-09"
    / "identity_bound_execution"
    / "etf_1077_identity_bound_execution_manifest.json"
)

POLICY_PATH = (
    ROOT
    / "config"
    / "market"
    / "authoritative_etf_taxonomy_registry_acquisition_policy.json"
)

AUTHORIZATION_PATH = (
    ROOT
    / "config"
    / "market"
    / "authoritative_etf_taxonomy_sec_capture_authorization.json"
)

EXPECTED_MANIFEST_SHA = (
    "9ed50f6e8ac414d347cb563a651067326"
    "31ec5a4c1c092142411900e19d03520"
)


class ProductionSECCaptureLaunchTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        if not CONTRACT_PATH.exists():  # gitignored local artifact (artifacts/), present only on the governed local run
            raise unittest.SkipTest(f"local governed artifact not present: {CONTRACT_PATH.name}")
        cls.contract = load_json(
            CONTRACT_PATH
        )

        cls.policy = load_json(
            POLICY_PATH
        )

        cls.authorization = load_json(
            AUTHORIZATION_PATH
        )

        cls.empty_submissions = json.dumps(
            {
                "filings": {
                    "recent": {
                        "form": [],
                        "accessionNumber": [],
                        "primaryDocument": [],
                        "filingDate": [],
                    }
                }
            }
        ).encode(
            "utf-8"
        )

    def test_frozen_identity_sha(self):
        digest = hashlib.sha256(
            CONTRACT_PATH.read_bytes()
        ).hexdigest()

        self.assertEqual(
            digest,
            EXPECTED_MANIFEST_SHA,
        )

    def test_current_policy_is_authorized_1_2(self):
        self.assertEqual(
            self.policy[
                "policy_version"
            ],
            "1.2.0",
        )

        self.assertTrue(
            self.policy[
                "authority"
            ][
                "authoritative_source_capture"
            ]
        )

    def test_current_authorization_is_production_1_1(self):
        self.assertEqual(
            self.authorization[
                "authorization_version"
            ],
            "1.1.0",
        )

        self.assertEqual(
            self.authorization[
                "execution_state"
            ],
            "AUTHORIZED_FOR_PRODUCTION_CAPTURE",
        )

        self.assertTrue(
            self.authorization[
                "production_execution_authorized"
            ]
        )

        self.assertTrue(
            self.authorization[
                "standard_route"
            ][
                "network_capture_authorized"
            ]
        )

        self.assertTrue(
            self.authorization[
                "standard_route"
            ][
                "authoritative_source_capture_authorized"
            ]
        )

    def test_authorized_launch_plan_is_full_population(self):
        result = build_launch_plan(
            self.contract,
            self.policy,
            self.authorization,
            identity_manifest_sha256=
                EXPECTED_MANIFEST_SHA,
        )

        self.assertEqual(
            result[
                "governed_population"
            ],
            1077,
        )

        self.assertEqual(
            result[
                "standard_registrant_count"
            ],
            102,
        )

        self.assertEqual(
            result[
                "standard_etf_count"
            ],
            862,
        )

        self.assertEqual(
            result[
                "remediation_registrant_count"
            ],
            1,
        )

        self.assertEqual(
            result[
                "remediation_etf_count"
            ],
            215,
        )

        self.assertEqual(
            result[
                "initial_submission_requests"
            ],
            102,
        )

        self.assertEqual(
            result[
                "maximum_unique_sec_requests"
            ],
            4412,
        )

        self.assertTrue(
            result[
                "production_execution_authorized"
            ]
        )

        self.assertEqual(
            result[
                "network_requests_performed"
            ],
            0,
        )

    def test_current_authorized_contract_executes_with_injected_transport(
        self,
    ):
        calls = []

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
                self.empty_submissions,
            )

        with tempfile.TemporaryDirectory() as temp:
            result = execute_live(
                self.contract,
                self.policy,
                self.authorization,
                identity_manifest_sha256=
                    EXPECTED_MANIFEST_SHA,
                user_agent=
                    "UIP research contact@example.com",
                raw_root=
                    temp,
                fetcher=
                    fake_fetcher,
            )

        self.assertEqual(
            len(calls),
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
                "record_count"
            ],
            1077,
        )

        self.assertEqual(
            result[
                "standard_etf_count"
            ],
            862,
        )

        self.assertEqual(
            result[
                "remediation_etf_count"
            ],
            215,
        )

        self.assertEqual(
            result[
                "unique_sec_requests_performed"
            ],
            102,
        )

        self.assertEqual(
            result[
                "taxonomy_classification_performed"
            ],
            0,
        )

        self.assertEqual(
            result[
                "taxonomy_normalization_performed"
            ],
            0,
        )

    def test_policy_downgrade_blocks_before_fetcher(self):
        policy = copy.deepcopy(
            self.policy
        )

        policy[
            "policy_version"
        ] = "1.1.0"

        policy[
            "authority"
        ][
            "authoritative_source_capture"
        ] = False

        calls = []

        def forbidden_fetcher(
            url,
            user_agent,
            timeout,
        ):
            calls.append(
                url
            )

            raise AssertionError(
                "Fetcher must remain unreachable."
            )

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(
                ProductionSECCaptureLaunchError
            ):
                execute_live(
                    self.contract,
                    policy,
                    self.authorization,
                    identity_manifest_sha256=
                        EXPECTED_MANIFEST_SHA,
                    user_agent=
                        "UIP research contact@example.com",
                    raw_root=
                        temp,
                    fetcher=
                        forbidden_fetcher,
                )

        self.assertEqual(
            calls,
            [],
        )

    def test_authorization_downgrade_blocks_before_fetcher(self):
        authorization = copy.deepcopy(
            self.authorization
        )

        authorization[
            "authorization_version"
        ] = "1.0.0"

        authorization[
            "execution_state"
        ] = "FROZEN_PENDING_POLICY_AUTHORIZATION"

        authorization[
            "production_execution_authorized"
        ] = False

        authorization[
            "standard_route"
        ][
            "network_capture_authorized"
        ] = False

        authorization[
            "standard_route"
        ][
            "authoritative_source_capture_authorized"
        ] = False

        calls = []

        def forbidden_fetcher(
            url,
            user_agent,
            timeout,
        ):
            calls.append(
                url
            )

            raise AssertionError(
                "Fetcher must remain unreachable."
            )

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(
                ProductionSECCaptureLaunchError
            ):
                execute_live(
                    self.contract,
                    self.policy,
                    authorization,
                    identity_manifest_sha256=
                        EXPECTED_MANIFEST_SHA,
                    user_agent=
                        "UIP research contact@example.com",
                    raw_root=
                        temp,
                    fetcher=
                        forbidden_fetcher,
                )

        self.assertEqual(
            calls,
            [],
        )

    def test_remediation_route_remains_standard_route_prohibited(self):
        remediation = (
            self.authorization[
                "remediation_route"
            ]
        )

        self.assertFalse(
            remediation[
                "standard_route_execution_authorized"
            ]
        )

        self.assertEqual(
            remediation[
                "member_count"
            ],
            215,
        )

        self.assertEqual(
            remediation[
                "delegated_executor"
            ],
            "EXISTING_SERIES_CLASS_REMEDIATION_ARCHITECTURE",
        )

    def test_downstream_authorities_all_remain_closed(self):
        downstream = (
            self.authorization[
                "downstream_authority"
            ]
        )

        self.assertTrue(
            all(
                value is False
                for value
                in downstream.values()
            )
        )

        policy_authority = (
            self.policy[
                "authority"
            ]
        )

        for field in (
            "production_taxonomy_classification",
            "production_taxonomy_certification",
            "benchmark_qualified_universe_publication",
            "relative_return_calculation",
            "risk_analytics",
            "forecasting",
            "ranking",
            "recommendations",
            "portfolio_allocation",
            "uip_export",
            "automatic_execution",
            "direct_uip_database_writes",
        ):
            self.assertFalse(
                policy_authority[
                    field
                ]
            )

    def test_runner_direct_file_invocation_builds_authorized_plan(self):
        runner = (
            ROOT
            / "scripts"
            / "run_authoritative_etf_taxonomy_sec_capture.py"
        )

        with tempfile.TemporaryDirectory() as temp:
            output = (
                Path(temp)
                / "must_not_exist.json"
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(runner),
                    "--identity-manifest",
                    str(CONTRACT_PATH),
                    "--policy",
                    str(POLICY_PATH),
                    "--authorization",
                    str(AUTHORIZATION_PATH),
                    "--raw-root",
                    str(
                        Path(temp)
                        / "raw"
                    ),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                msg=(
                    completed.stdout
                    + "\n"
                    + completed.stderr
                ),
            )

            self.assertFalse(
                output.exists()
            )

            plan = json.loads(
                completed.stdout
            )

            self.assertTrue(
                plan[
                    "production_execution_authorized"
                ]
            )

            self.assertEqual(
                plan[
                    "governed_population"
                ],
                1077,
            )

            self.assertEqual(
                plan[
                    "initial_submission_requests"
                ],
                102,
            )

            self.assertEqual(
                plan[
                    "network_requests_performed"
                ],
                0,
            )


if __name__ == "__main__":
    unittest.main()
