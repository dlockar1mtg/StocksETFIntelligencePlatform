from __future__ import annotations

import copy
import json
import unittest

from foundation.market.sec_series_class_resolution_pilot_execution_authorization import (
    SeriesClassPilotAuthorizationError,
    build_authorization,
    sha256_bytes,
)


class SeriesClassPilotAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.head = (
            "b652796a86dda104aa2b6b1b592274b4f10f8538"
        )

        self.resolution_policy = {
            "required_remediation_ledger_sha256": (
                "5311e079e64dda290268296fe99653b94335bfe89f97eca77808210c018a82ad"
            ),
            "required_pilot_record_count": 5,
            "pilot_symbols": [
                "AAXJ",
                "ACWI",
                "IBTJ",
                "IWN",
                "VLUE",
            ],
            "route": {
                "maximum_recent_filings_scanned": 5,
                "maximum_documents_per_filing": 12,
                "required_identity_markers": [
                    "sec_series_id",
                    "sec_class_contract_id",
                ],
                "supporting_identity_markers": [
                    "symbol",
                    "sec_cik",
                ],
            },
            "execution": {
                "maximum_total_sec_requests": 66,
                "maximum_requests_per_second": 1,
                "maximum_retry_attempts": 0,
                "request_timeout_seconds": 45,
                "cache_identical_requests": True,
                "immutable_raw_storage": True,
                "pilot_only": True,
            },
            "authority": {
                "series_class_route_reliability_certification": False,
                "full_priority_batch_recapture": False,
                "capture_ledger_certification": False,
                "taxonomy_evidence_normalization": False,
                "production_taxonomy_classification": False,
                "relative_return_calculation": False,
                "risk_analytics": False,
                "forecasting": False,
                "ranking": False,
                "recommendations": False,
                "portfolio_allocation": False,
                "uip_export": False,
                "automatic_execution": False,
                "direct_uip_database_writes": False,
            },
        }

        self.policy = {
            "required_governed_head": self.head,
            "required_resolution_policy_sha256": "",
            "required_remediation_ledger_sha256": (
                self.resolution_policy["required_remediation_ledger_sha256"]
            ),
            "required_record_count": 5,
            "required_symbols": [
                "AAXJ",
                "ACWI",
                "IBTJ",
                "IWN",
                "VLUE",
            ],
            "operating_date": "2026-08-08",
            "operating_timezone": "America/Chicago",
            "execution_contract": {
                "maximum_recent_filings_scanned": 5,
                "maximum_documents_per_filing": 12,
                "maximum_total_sec_requests": 66,
                "maximum_requests_per_second": 1,
                "maximum_retry_attempts": 0,
                "request_timeout_seconds": 45,
                "cache_identical_requests": True,
                "immutable_raw_storage": True,
                "declared_sec_user_agent_required": True,
                "pilot_only": True,
            },
            "identity_contract": {},
            "scope_controls": {},
            "authority": {},
        }

    def _build(
        self,
        resolution_policy=None,
    ):
        resolution = copy.deepcopy(
            resolution_policy or self.resolution_policy
        )

        payload = json.dumps(
            resolution,
            sort_keys=True,
        ).encode("utf-8")

        policy = copy.deepcopy(
            self.policy
        )

        policy[
            "required_resolution_policy_sha256"
        ] = sha256_bytes(payload)

        return build_authorization(
            resolution,
            payload,
            policy,
            self.head,
        )

    def test_valid_contract_authorizes_exact_pilot(self):
        authorization = self._build()

        self.assertEqual(
            authorization["authorized_symbols"],
            [
                "AAXJ",
                "ACWI",
                "IBTJ",
                "IWN",
                "VLUE",
            ],
        )

        self.assertEqual(
            authorization[
                "execution_contract"
            ][
                "maximum_total_sec_requests"
            ],
            66,
        )

        self.assertTrue(
            authorization["network_capture_authorized"]
        )

        self.assertFalse(
            authorization["full_215_execution_authorized"]
        )

    def test_symbol_scope_drift_fails_closed(self):
        resolution = copy.deepcopy(
            self.resolution_policy
        )
        resolution["pilot_symbols"][1] = "IAI"

        with self.assertRaises(
            SeriesClassPilotAuthorizationError
        ):
            self._build(resolution)

    def test_retry_drift_fails_closed(self):
        resolution = copy.deepcopy(
            self.resolution_policy
        )
        resolution["execution"]["maximum_retry_attempts"] = 1

        with self.assertRaises(
            SeriesClassPilotAuthorizationError
        ):
            self._build(resolution)

    def test_request_ceiling_drift_fails_closed(self):
        resolution = copy.deepcopy(
            self.resolution_policy
        )
        resolution["execution"]["maximum_total_sec_requests"] = 67

        with self.assertRaises(
            SeriesClassPilotAuthorizationError
        ):
            self._build(resolution)

    def test_full_population_authority_fails_closed(self):
        resolution = copy.deepcopy(
            self.resolution_policy
        )
        resolution[
            "authority"
        ][
            "full_priority_batch_recapture"
        ] = True

        with self.assertRaises(
            SeriesClassPilotAuthorizationError
        ):
            self._build(resolution)


if __name__ == "__main__":
    unittest.main()
