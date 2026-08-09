from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from foundation.market.sec_historical_submission_shard_capture import (
    HistoricalShardCaptureError,
    canonical_json_bytes,
    capture_historical_shards,
    sha256_bytes,
    validate_manifest,
)


class Phase36B3RTests(
    unittest.TestCase
):
    def manifest(self):
        shards = []

        for index in range(
            1,
            13,
        ):
            name = (
                "CIK0001100663-"
                f"submissions-{index:03d}.json"
            )

            shards.append(
                {
                    "filename": name,
                    "url": (
                        "https://data.sec.gov/"
                        "submissions/"
                        + name
                    ),
                    "filing_from": "2020-01-01",
                    "filing_to": "2020-12-31",
                    "filing_count": 10,
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
            "target_record_count": 4,
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
                "full_priority_population_execution_authorized": False,
                "taxonomy_evidence_normalization_authorized": False,
            },
        }

    def authorization(
        self,
        manifest_sha,
    ):
        return {
            "manifest_sha256": manifest_sha,
            "network_capture_authorized": True,
            "automatic_execution_authorized": False,
            "filing_header_capture_authorized": False,
            "filing_document_capture_authorized": False,
            "full_215_execution_authorized": False,
            "taxonomy_normalization_authorized": False,
            "execution_contract": {
                "maximum_unique_sec_requests": 12,
                "maximum_requests_per_second": 1,
                "maximum_retry_attempts": 0,
                "request_timeout_seconds": 45,
            },
        }

    def test_manifest_validation_locks_exact_12_urls(
        self,
    ):
        manifest = self.manifest()

        payload = canonical_json_bytes(
            manifest
        )

        shards = validate_manifest(
            manifest,
            sha256_bytes(
                payload
            ),
            payload,
        )

        self.assertEqual(
            len(shards),
            12,
        )

    def test_manifest_sha_drift_fails_closed(
        self,
    ):
        manifest = self.manifest()

        payload = canonical_json_bytes(
            manifest
        )

        with self.assertRaises(
            HistoricalShardCaptureError
        ):
            validate_manifest(
                manifest,
                "0" * 64,
                payload,
            )

    def test_extra_shard_fails_closed(
        self,
    ):
        manifest = self.manifest()

        manifest[
            "historical_shards"
        ].append(
            {
                "filename": "unexpected.json",
                "url": (
                    "https://data.sec.gov/"
                    "submissions/unexpected.json"
                ),
            }
        )

        manifest[
            "historical_shard_count"
        ] = 13

        payload = canonical_json_bytes(
            manifest
        )

        with self.assertRaises(
            HistoricalShardCaptureError
        ):
            validate_manifest(
                manifest,
                sha256_bytes(
                    payload
                ),
                payload,
            )

    def test_retry_authority_is_zero(
        self,
    ):
        manifest = self.manifest()

        manifest[
            "execution_contract"
        ][
            "maximum_retry_attempts"
        ] = 1

        payload = canonical_json_bytes(
            manifest
        )

        with self.assertRaises(
            HistoricalShardCaptureError
        ):
            validate_manifest(
                manifest,
                sha256_bytes(
                    payload
                ),
                payload,
            )

    def test_network_requires_separate_authorization(
        self,
    ):
        manifest = self.manifest()

        payload = canonical_json_bytes(
            manifest
        )

        shards = validate_manifest(
            manifest,
            sha256_bytes(
                payload
            ),
            payload,
        )

        authorization = (
            self.authorization(
                sha256_bytes(
                    payload
                )
            )
        )

        authorization[
            "network_capture_authorized"
        ] = False

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(
                HistoricalShardCaptureError
            ):
                capture_historical_shards(
                    manifest,
                    shards,
                    authorization,
                    sha256_bytes(payload),
                    directory,
                    "Test test@example.com",
                )

    @patch(
        "foundation.market."
        "sec_historical_submission_shard_capture."
        "time.sleep",
        return_value=None,
    )
    @patch(
        "foundation.market."
        "sec_historical_submission_shard_capture."
        "fetch_once",
    )
    def test_capture_is_exactly_12_requests(
        self,
        mock_fetch,
        _mock_sleep,
    ):
        manifest = self.manifest()

        payload = (
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()

        manifest_sha = sha256_bytes(
            payload
        )

        shards = validate_manifest(
            manifest,
            manifest_sha,
            payload,
        )

        mock_payload = json.dumps(
            {
                "accessionNumber": [
                    "0000000000-00-000001"
                ]
            }
        ).encode()

        mock_fetch.return_value = (
            200,
            "https://data.sec.gov/test",
            mock_payload,
        )

        authorization = (
            self.authorization(
                manifest_sha
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            ledger = capture_historical_shards(
                manifest,
                shards,
                authorization,
                    sha256_bytes(payload),
                directory,
                "Test test@example.com",
            )

        self.assertEqual(
            mock_fetch.call_count,
            12,
        )

        self.assertEqual(
            ledger[
                "request_count"
            ],
            12,
        )

        self.assertTrue(
            ledger[
                "capture_complete"
            ]
        )

        self.assertFalse(
            ledger[
                "filing_header_capture_authorized"
            ]
        )

        self.assertFalse(
            ledger[
                "taxonomy_evidence_normalization_authorized"
            ]
        )


if __name__ == "__main__":
    unittest.main()
