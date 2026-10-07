from __future__ import annotations

import json
import unittest

from foundation.market.sec_historical_submission_shard_capture_execution_authorization import (
    HistoricalShardAuthorizationError,
    build_authorization,
    sha256_bytes,
    validate_manifest,
)


class Phase36B3RExecutionAuthorizationTests(
    unittest.TestCase
):
    def manifest(self):
        shards = []

        for index in range(
            1,
            13,
        ):
            filename = (
                "CIK0001100663-"
                f"submissions-{index:03d}.json"
            )

            shards.append(
                {
                    "filename": filename,
                    "url": (
                        "https://data.sec.gov/"
                        "submissions/"
                        + filename
                    ),
                }
            )

        return {
            "phase": "3.6b.3r",
            "target_symbols": [
                "AAXJ",
                "ACWI",
                "IBTJ",
                "IWN",
            ],
            "historical_shard_count": 12,
            "historical_shards": shards,
            "execution_contract": {
                "maximum_unique_sec_requests": 12,
                "maximum_requests_per_second": 1,
                "maximum_retry_attempts": 0,
                "cache_identical_requests": True,
                "immutable_raw_storage": True,
            },
            "authority": {
                "historical_shard_network_capture_authorized": False,
                "filing_header_capture_authorized": False,
                "filing_document_capture_authorized": False,
                "expanded_recent_filing_scan_authorized": False,
                "full_priority_population_execution_authorized": False,
                "taxonomy_evidence_normalization_authorized": False,
                "production_taxonomy_classification_authorized": False,
                "ranking_authorized": False,
                "recommendations_authorized": False,
                "portfolio_allocation_authorized": False,
                "automatic_execution_authorized": False,
                "uip_database_write_authorized": False,
            },
        }

    def policy(
        self,
        manifest_sha,
    ):
        return {
            "required_governed_head": (
                "a" * 40
            ),
            "required_manifest_sha256": (
                manifest_sha
            ),
            "required_target_symbols": [
                "AAXJ",
                "ACWI",
                "IBTJ",
                "IWN",
            ],
            "required_shard_count": 12,
            "operating_date": "2026-08-08",
            "operating_timezone": (
                "America/Chicago"
            ),
            "execution_contract": {
                "maximum_unique_sec_requests": 12,
                "maximum_requests_per_second": 1,
                "maximum_retry_attempts": 0,
                "request_timeout_seconds": 45,
                "cache_identical_requests": True,
                "immutable_raw_storage": True,
            },
            "scope_controls": {},
            "authority": {},
        }

    def test_authorization_locks_manifest_and_head(
        self,
    ):
        manifest = self.manifest()

        payload = (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

        policy = self.policy(
            sha256_bytes(
                payload
            )
        )

        authorization = build_authorization(
            manifest,
            payload,
            policy,
            "a" * 40,
        )

        self.assertTrue(
            authorization[
                "network_capture_authorized"
            ]
        )

        self.assertEqual(
            authorization[
                "authorized_shard_count"
            ],
            12,
        )

    def test_head_drift_fails_closed(
        self,
    ):
        manifest = self.manifest()

        payload = (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

        policy = self.policy(
            sha256_bytes(
                payload
            )
        )

        with self.assertRaises(
            HistoricalShardAuthorizationError
        ):
            validate_manifest(
                manifest,
                payload,
                policy,
                "b" * 40,
            )

    def test_manifest_sha_drift_fails_closed(
        self,
    ):
        manifest = self.manifest()

        payload = (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

        policy = self.policy(
            "0" * 64
        )

        with self.assertRaises(
            HistoricalShardAuthorizationError
        ):
            validate_manifest(
                manifest,
                payload,
                policy,
                "a" * 40,
            )

    def test_manifest_cannot_self_authorize_network(
        self,
    ):
        manifest = self.manifest()

        manifest[
            "authority"
        ][
            "historical_shard_network_capture_authorized"
        ] = True

        payload = (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

        policy = self.policy(
            sha256_bytes(
                payload
            )
        )

        with self.assertRaises(
            HistoricalShardAuthorizationError
        ):
            validate_manifest(
                manifest,
                payload,
                policy,
                "a" * 40,
            )

    def test_authorization_keeps_downstream_closed(
        self,
    ):
        manifest = self.manifest()

        payload = (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

        policy = self.policy(
            sha256_bytes(
                payload
            )
        )

        authorization = build_authorization(
            manifest,
            payload,
            policy,
            "a" * 40,
        )

        self.assertFalse(
            authorization[
                "filing_header_capture_authorized"
            ]
        )

        self.assertFalse(
            authorization[
                "filing_document_capture_authorized"
            ]
        )

        self.assertFalse(
            authorization[
                "full_215_execution_authorized"
            ]
        )

        self.assertFalse(
            authorization[
                "taxonomy_normalization_authorized"
            ]
        )


if __name__ == "__main__":
    unittest.main()
