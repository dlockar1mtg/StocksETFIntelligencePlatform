from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_capture_runner import (
    AuthoritativeTaxonomyCaptureRunnerError,
    build_execution_manifest,
)

ROOT = Path(__file__).resolve().parents[2]

PLAN_PATH = (
    ROOT
    / "artifacts"
    / "analysis"
    / "phase_3_model_taxonomy_production"
    / "2026-08-09"
    / "authoritative_capture_plan"
    / "etf_1077_authoritative_capture_plan.json"
)

POLICY_PATH = (
    ROOT
    / "config"
    / "market"
    / "authoritative_etf_taxonomy_registry_acquisition_policy.json"
)


class AuthoritativeTaxonomyCaptureRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(
            PLAN_PATH.read_text(
                encoding="utf-8-sig"
            )
        )

        cls.policy = json.loads(
            POLICY_PATH.read_text(
                encoding="utf-8-sig"
            )
        )

    def test_full_population_is_preserved(self) -> None:
        result = build_execution_manifest(
            self.plan,
            self.policy,
        )

        self.assertEqual(
            result["summary"]["governed_population"],
            1077,
        )

        self.assertEqual(
            result["summary"]["registrant_group_count"],
            103,
        )

        security_ids = [
            security_id
            for group in result["execution_groups"]
            for security_id in group["security_ids"]
        ]

        self.assertEqual(
            len(security_ids),
            1077,
        )

        self.assertEqual(
            len(set(security_ids)),
            1077,
        )

    def test_standard_and_remediation_lanes_are_exact(self) -> None:
        result = build_execution_manifest(
            self.plan,
            self.policy,
        )

        summary = result["summary"]

        self.assertEqual(
            summary["standard_registrant_count"],
            102,
        )

        self.assertEqual(
            summary["standard_etf_count"],
            862,
        )

        self.assertEqual(
            summary["remediation_registrant_count"],
            1,
        )

        self.assertEqual(
            summary["remediation_etf_count"],
            215,
        )

    def test_current_policy_prohibits_live_capture(self) -> None:
        with self.assertRaises(
            AuthoritativeTaxonomyCaptureRunnerError
        ):
            build_execution_manifest(
                self.plan,
                self.policy,
                live_network_requested=True,
            )

    def test_offline_manifest_performs_zero_requests(self) -> None:
        result = build_execution_manifest(
            self.plan,
            self.policy,
        )

        self.assertEqual(
            result["summary"]["network_requests_performed"],
            0,
        )

        self.assertEqual(
            result["summary"]["sec_requests_performed"],
            0,
        )

    def test_remediation_group_uses_existing_architecture(self) -> None:
        result = build_execution_manifest(
            self.plan,
            self.policy,
        )

        remediation = [
            group
            for group in result["execution_groups"]
            if group["lane"]
            == "GOVERNED_EXISTING_REMEDIATION_ROUTE"
        ]

        self.assertEqual(
            len(remediation),
            1,
        )

        self.assertEqual(
            remediation[0]["etf_count"],
            215,
        )

        self.assertEqual(
            remediation[0]["executor"],
            "EXISTING_SERIES_CLASS_REMEDIATION_ARCHITECTURE",
        )

    def test_standard_groups_do_not_use_remediation_executor(self) -> None:
        result = build_execution_manifest(
            self.plan,
            self.policy,
        )

        standard = [
            group
            for group in result["execution_groups"]
            if group["lane"]
            == "STANDARD_REGISTRANT_AUTHORITY_ACQUISITION"
        ]

        self.assertEqual(
            len(standard),
            102,
        )

        self.assertTrue(
            all(
                group["executor"]
                == "STANDARD_REGISTRANT_CAPTURE"
                for group in standard
            )
        )

    def test_classification_and_normalization_remain_closed(self) -> None:
        result = build_execution_manifest(
            self.plan,
            self.policy,
        )

        self.assertEqual(
            result["summary"]["taxonomy_classification_performed"],
            0,
        )

        self.assertEqual(
            result["summary"]["taxonomy_normalization_performed"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
