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
        cls.contract = load_json(
            CONTRACT_PATH
        )

        cls.policy = load_json(
            POLICY_PATH
        )

        cls.authorization = load_json(
            AUTHORIZATION_PATH
        )

    def test_frozen_identity_sha(self):
        digest = hashlib.sha256(
            CONTRACT_PATH.read_bytes()
        ).hexdigest()

        self.assertEqual(
            digest,
            EXPECTED_MANIFEST_SHA,
        )

    def test_offline_launch_plan_is_full_population(self):
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

        self.assertFalse(
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

    def test_runner_direct_file_invocation_builds_offline_plan(self):
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

    def test_current_policy_blocks_live_before_fetcher(self):
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
                "Real/fake fetcher must not be reached."
            )

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(
                ProductionSECCaptureLaunchError
            ):
                execute_live(
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
                        forbidden_fetcher,
                )

        self.assertEqual(
            calls,
            [],
        )

    def test_authorization_alone_cannot_open_live_capture(self):
        authorization = copy.deepcopy(
            self.authorization
        )

        authorization[
            "production_execution_authorized"
        ] = True

        authorization[
            "standard_route"
        ][
            "network_capture_authorized"
        ] = True

        authorization[
            "standard_route"
        ][
            "authoritative_source_capture_authorized"
        ] = True

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

    def test_future_authorized_contract_can_use_injected_transport(self):
        policy = copy.deepcopy(
            self.policy
        )

        policy[
            "policy_version"
        ] = "1.2.0"

        policy[
            "authority"
        ][
            "authoritative_source_capture"
        ] = True

        authorization = copy.deepcopy(
            self.authorization
        )

        authorization[
            "production_execution_authorized"
        ] = True

        authorization[
            "execution_state"
        ] = "AUTHORIZED_FOR_PRODUCTION_CAPTURE"

        authorization[
            "standard_route"
        ][
            "network_capture_authorized"
        ] = True

        authorization[
            "standard_route"
        ][
            "authoritative_source_capture_authorized"
        ] = True

        empty_submissions = json.dumps(
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
                empty_submissions,
            )

        with tempfile.TemporaryDirectory() as temp:
            result = execute_live(
                self.contract,
                policy,
                authorization,
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

    def test_remediation_route_never_self_authorizes_standard_route(self):
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

    def test_downstream_authorities_all_closed(self):
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


if __name__ == "__main__":
    unittest.main()
