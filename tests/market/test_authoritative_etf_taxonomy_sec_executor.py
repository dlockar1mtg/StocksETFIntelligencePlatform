from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_sec_executor import (
    AuthoritativeTaxonomySECExecutorError,
    build_request_plan,
    execute_authorized_capture,
    filing_document_url,
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

    def test_identity_contract_sha_is_frozen(
        self,
    ) -> None:
        digest = hashlib.sha256(
            CONTRACT_PATH.read_bytes()
        ).hexdigest()

        self.assertEqual(
            digest,
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
            for group in groups
            for member
            in group["security_identities"]
        ]

        self.assertEqual(
            len(members),
            1077,
        )

        self.assertEqual(
            len(
                {
                    member["security_id"]
                    for member in members
                }
            ),
            1077,
        )

    def test_request_plan_is_103_registrants(
        self,
    ) -> None:
        plan = build_request_plan(
            self.contract
        )

        self.assertEqual(
            plan[
                "unique_submission_request_count"
            ],
            103,
        )

        self.assertEqual(
            len(plan["requests"]),
            103,
        )

        self.assertEqual(
            sum(
                item["member_count"]
                for item
                in plan["requests"]
            ),
            1077,
        )

    def test_current_governance_blocks_before_fetcher(
        self,
    ) -> None:
        calls = []

        def forbidden_fetcher(
            url: str,
            user_agent: str,
            timeout: int,
        ):
            calls.append(url)

            raise AssertionError(
                "Fetcher must not be reached."
            )

        authorization = {
            "network_capture_authorized": True,
            "authoritative_source_capture_authorized": True,
            "identity_bound_manifest_sha256":
                EXPECTED_CONTRACT_SHA,
            "maximum_unique_sec_requests": 10000,
            "maximum_requests_per_second": 1,
            "maximum_candidate_filings_per_security": 5,
            "request_timeout_seconds": 30,
            "production_taxonomy_classification_authorized": False,
            "taxonomy_normalization_authorized": False,
        }

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(
                AuthoritativeTaxonomySECExecutorError
            ):
                execute_authorized_capture(
                    self.contract,
                    self.policy,
                    authorization,
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

    def test_submissions_url_is_cik_bound(
        self,
    ) -> None:
        self.assertEqual(
            submissions_url("1100663"),
            (
                "https://data.sec.gov/submissions/"
                "CIK0001100663.json"
            ),
        )

    def test_document_url_is_accession_bound(
        self,
    ) -> None:
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

    def test_fake_transport_executes_all_1077(
        self,
    ) -> None:
        policy = copy.deepcopy(
            self.policy
        )

        policy["authority"][
            "authoritative_source_capture"
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
        ).encode("utf-8")

        calls = []

        def fake_fetcher(
            url: str,
            user_agent: str,
            timeout: int,
        ):
            calls.append(url)

            return (
                200,
                url,
                empty_submissions,
            )

        authorization = {
            "network_capture_authorized": True,
            "authoritative_source_capture_authorized": True,
            "identity_bound_manifest_sha256":
                EXPECTED_CONTRACT_SHA,
            "maximum_unique_sec_requests": 103,
            "maximum_requests_per_second": 1,
            "maximum_candidate_filings_per_security": 5,
            "request_timeout_seconds": 30,
            "production_taxonomy_classification_authorized": False,
            "taxonomy_normalization_authorized": False,
        }

        with tempfile.TemporaryDirectory() as temp:
            result = execute_authorized_capture(
                self.contract,
                policy,
                authorization,
                manifest_sha256=
                    EXPECTED_CONTRACT_SHA,
                user_agent=
                    "UIP research contact@example.com",
                raw_root=temp,
                fetcher=fake_fetcher,
                sleeper=lambda _: None,
            )

            raw_files = list(
                (
                    Path(temp)
                    / "sec_taxonomy"
                    / "submissions"
                ).glob("*.json")
            )

            self.assertEqual(
                len(raw_files),
                103,
            )

        self.assertEqual(
            result["record_count"],
            1077,
        )

        self.assertEqual(
            result[
                "unique_sec_requests_performed"
            ],
            103,
        )

        self.assertEqual(
            len(calls),
            103,
        )

        self.assertEqual(
            len(set(calls)),
            103,
        )

        self.assertEqual(
            result[
                "acquisition_state_counts"
            ],
            {
                "UNRESOLVED": 1077
            },
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

        second["security_id"] = (
            first["security_id"]
        )

        with self.assertRaises(
            AuthoritativeTaxonomySECExecutorError
        ):
            validate_identity_contract(
                contract
            )


if __name__ == "__main__":
    unittest.main()
