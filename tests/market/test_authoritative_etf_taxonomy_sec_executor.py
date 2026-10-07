from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_sec_executor import (
    AuthoritativeTaxonomySECExecutorError,
    REMEDIATION_LANE,
    STANDARD_LANE,
    build_request_plan,
    execute_authorized_capture,
    filing_document_url,
    issuer_key_for_cik,
    submissions_url,
    validate_identity_contract,
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

EXPECTED_CONTRACT_SHA = (
    "9ed50f6e8ac414d347cb563a651067326"
    "31ec5a4c1c092142411900e19d03520"
)


class AuthoritativeTaxonomySECExecutorTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        if not CONTRACT_PATH.exists():  # gitignored local artifact (artifacts/), present only on the governed local run
            raise unittest.SkipTest(f"local governed artifact not present: {CONTRACT_PATH.name}")
        cls.contract = json.loads(
            CONTRACT_PATH.read_text(
                encoding="utf-8-sig"
            )
        )

        cls.policy = json.loads(
            POLICY_PATH.read_text(
                encoding="utf-8"
            )
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
        ).encode("utf-8")

    def enabled_policy(self):
        policy = copy.deepcopy(
            self.policy
        )

        policy["authority"][
            "authoritative_source_capture"
        ] = True

        return policy

    def authorization(self):
        return {
            "network_capture_authorized":
                True,

            "authoritative_source_capture_authorized":
                True,

            "identity_bound_manifest_sha256":
                EXPECTED_CONTRACT_SHA,

            "maximum_unique_sec_requests":
                5000,

            "maximum_requests_per_second":
                1,

            "maximum_candidate_filings_per_security":
                5,

            "request_timeout_seconds":
                30,

            "production_taxonomy_classification_authorized":
                False,

            "taxonomy_normalization_authorized":
                False,
        }

    def fake_full_run(self):
        calls = []

        def fake_fetcher(
            url: str,
            user_agent: str,
            timeout: int,
        ):
            calls.append(
                url
            )

            return (
                200,
                url,
                self.empty_submissions,
            )

        temp = tempfile.TemporaryDirectory()

        result = execute_authorized_capture(
            self.contract,
            self.enabled_policy(),
            self.authorization(),
            manifest_sha256=
                EXPECTED_CONTRACT_SHA,
            user_agent=
                "UIP research contact@example.com",
            raw_root=temp.name,
            fetcher=fake_fetcher,
            sleeper=lambda _: None,
        )

        return (
            temp,
            result,
            calls,
        )

    def test_identity_contract_sha_is_frozen(
        self,
    ) -> None:
        self.assertEqual(
            hashlib.sha256(
                CONTRACT_PATH.read_bytes()
            ).hexdigest(),
            EXPECTED_CONTRACT_SHA,
        )

    def test_full_population_validates(
        self,
    ) -> None:
        groups = validate_identity_contract(
            self.contract
        )

        self.assertEqual(
            len(groups),
            103,
        )

        members = [
            member
            for group
            in groups
            for member
            in group[
                "security_identities"
            ]
        ]

        self.assertEqual(
            len(members),
            1077,
        )

    def test_executor_accepts_policy_1_2_contract(
        self,
    ) -> None:
        policy = copy.deepcopy(
            self.policy
        )

        policy["policy_version"] = "1.2.0"

        policy["authority"][
            "authoritative_source_capture"
        ] = True

        # This validates the executor policy contract only.
        # No fetcher is called here.
        from foundation.market.authoritative_etf_taxonomy_sec_executor import (
            validate_policy,
        )

        validate_policy(
            policy
        )

    def test_executor_rejects_unknown_policy_version(
        self,
    ) -> None:
        policy = copy.deepcopy(
            self.policy
        )

        policy["policy_version"] = "9.9.9"

        from foundation.market.authoritative_etf_taxonomy_sec_executor import (
            validate_policy,
        )

        with self.assertRaises(
            AuthoritativeTaxonomySECExecutorError
        ):
            validate_policy(
                policy
            )

    def test_request_plan_has_102_network_groups_and_one_delegated_group(
        self,
    ) -> None:
        plan = build_request_plan(
            self.contract
        )

        self.assertEqual(
            plan[
                "registrant_group_count"
            ],
            103,
        )

        self.assertEqual(
            plan[
                "unique_submission_request_count"
            ],
            102,
        )

        self.assertEqual(
            len(
                plan[
                    "network_requests"
                ]
            ),
            102,
        )

        self.assertEqual(
            sum(
                item[
                    "member_count"
                ]
                for item
                in plan[
                    "network_requests"
                ]
            ),
            862,
        )

        self.assertEqual(
            len(
                plan[
                    "delegated_remediation_groups"
                ]
            ),
            1,
        )

        self.assertEqual(
            plan[
                "delegated_remediation_groups"
            ][0][
                "member_count"
            ],
            215,
        )

    def test_closed_policy_blocks_before_fetcher(
        self,
    ) -> None:
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
            url: str,
            user_agent: str,
            timeout: int,
        ):
            calls.append(
                url
            )

            raise AssertionError(
                "Fetcher must not be reached."
            )

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(
                AuthoritativeTaxonomySECExecutorError
            ):
                execute_authorized_capture(
                    self.contract,
                    policy,
                    self.authorization(),
                    manifest_sha256=
                        EXPECTED_CONTRACT_SHA,
                    user_agent=
                        "UIP research contact@example.com",
                    raw_root=temp,
                    fetcher=forbidden_fetcher,
                    sleeper=lambda _: None,
                )

        self.assertEqual(
            calls,
            [],
        )

    def test_urls_are_structurally_bound(
        self,
    ) -> None:
        self.assertEqual(
            submissions_url(
                "1100663"
            ),
            (
                "https://data.sec.gov/submissions/"
                "CIK0001100663.json"
            ),
        )

        self.assertEqual(
            filing_document_url(
                "0001100663",
                "0001193125-26-000001",
                "example.htm",
            ),
            (
                "https://www.sec.gov/Archives/edgar/data/"
                "1100663/"
                "000119312526000001/"
                "example.htm"
            ),
        )

        self.assertEqual(
            issuer_key_for_cik(
                "1100663"
            ),
            "SEC-REGISTRANT-CIK-0001100663",
        )

    def test_full_fake_execution_preserves_all_1077(
        self,
    ) -> None:
        temp, result, calls = (
            self.fake_full_run()
        )

        try:
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

        finally:
            temp.cleanup()

    def test_remediation_lane_performs_zero_standard_route_requests(
        self,
    ) -> None:
        temp, result, calls = (
            self.fake_full_run()
        )

        try:
            remediation_group = next(
                group
                for group
                in self.contract[
                    "execution_groups"
                ]
                if group[
                    "lane"
                ]
                == REMEDIATION_LANE
            )

            prohibited_url = submissions_url(
                remediation_group[
                    "sec_cik"
                ]
            )

            self.assertNotIn(
                prohibited_url,
                calls,
            )

            remediation_records = [
                record
                for record
                in result[
                    "records"
                ]
                if record[
                    "lane"
                ]
                == REMEDIATION_LANE
            ]

            self.assertEqual(
                len(
                    remediation_records
                ),
                215,
            )

            self.assertTrue(
                all(
                    record[
                        "review_state"
                    ]
                    == "GOVERNED_REMEDIATION_ROUTE_PRESERVED"
                    for record
                    in remediation_records
                )
            )

            self.assertTrue(
                all(
                    record[
                        "evaluated_candidate_count"
                    ]
                    == 0
                    for record
                    in remediation_records
                )
            )

            self.assertTrue(
                all(
                    record[
                        "acquisition_reasons"
                    ]
                    == [
                        "GOVERNED_EXISTING_REMEDIATION_ROUTE_REQUIRED"
                    ]
                    for record
                    in remediation_records
                )
            )

        finally:
            temp.cleanup()

    def test_standard_lane_is_exactly_862_records(
        self,
    ) -> None:
        temp, result, calls = (
            self.fake_full_run()
        )

        try:
            standard = [
                record
                for record
                in result[
                    "records"
                ]
                if record[
                    "lane"
                ]
                == STANDARD_LANE
            ]

            self.assertEqual(
                len(
                    standard
                ),
                862,
            )

            self.assertEqual(
                result[
                    "acquisition_reason_counts"
                ][
                    "PRODUCT_SPECIFIC_SEC_FILING_NOT_RESOLVED"
                ],
                862,
            )

            self.assertEqual(
                result[
                    "acquisition_reason_counts"
                ][
                    "GOVERNED_EXISTING_REMEDIATION_ROUTE_REQUIRED"
                ],
                215,
            )

        finally:
            temp.cleanup()

    def test_phase_3_acquisition_required_fields_are_present(
        self,
    ) -> None:
        temp, result, calls = (
            self.fake_full_run()
        )

        try:
            required_fields = set(
                self.policy[
                    "required_manifest_fields"
                ]
            )

            for record in result[
                "records"
            ]:
                self.assertTrue(
                    required_fields.issubset(
                        record.keys()
                    )
                )

                self.assertTrue(
                    record[
                        "issuer_key"
                    ]
                )

                self.assertTrue(
                    record[
                        "acquisition_reasons"
                    ]
                )

                self.assertFalse(
                    record[
                        "taxonomy_dimensions_assigned"
                    ]
                )

        finally:
            temp.cleanup()

    def test_submissions_storage_is_content_addressed(
        self,
    ) -> None:
        temp, result, calls = (
            self.fake_full_run()
        )

        try:
            expected_sha = hashlib.sha256(
                self.empty_submissions
            ).hexdigest()

            root = (
                Path(
                    temp.name
                )
                / "sec_taxonomy"
                / "submissions"
            )

            raw_files = list(
                root.rglob(
                    "*.json"
                )
            )

            self.assertEqual(
                len(
                    raw_files
                ),
                102,
            )

            self.assertTrue(
                all(
                    file.stem
                    == expected_sha
                    for file
                    in raw_files
                )
            )

            self.assertEqual(
                len(
                    {
                        file.parent.name
                        for file
                        in raw_files
                    }
                ),
                102,
            )

        finally:
            temp.cleanup()

    def test_duplicate_identity_fails_closed(
        self,
    ) -> None:
        contract = copy.deepcopy(
            self.contract
        )

        first = (
            contract[
                "execution_groups"
            ][0][
                "security_identities"
            ][0]
        )

        second = (
            contract[
                "execution_groups"
            ][1][
                "security_identities"
            ][0]
        )

        second[
            "security_id"
        ] = first[
            "security_id"
        ]

        with self.assertRaises(
            AuthoritativeTaxonomySECExecutorError
        ):
            validate_identity_contract(
                contract
            )


if __name__ == "__main__":
    unittest.main()
