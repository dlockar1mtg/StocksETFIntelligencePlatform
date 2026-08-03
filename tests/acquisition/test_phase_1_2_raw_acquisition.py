from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.acquisition.raw_capture import (
    RawCaptureError,
    load_json,
    sha256_bytes,
    validate_capture_manifest,
    validate_capture_policy,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc)


class Phase12RawAcquisitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_json(ROOT / "config/acquisition/raw_capture_policy.json")
        provider_contracts = load_json(ROOT / "config/providers/provider_contracts.json")
        security_master = load_json(ROOT / "config/security/security_master.json")
        self.provider_ids = {"PROVIDER-TEST"}
        self.domains = set(provider_contracts["governed_domains"])
        self.security_ids = {item["security_id"] for item in security_master["securities"]}
        self.manifest = {
            "capture_id": "CAP-TEST-001",
            "provider_id": "PROVIDER-TEST",
            "data_domain": "raw_price",
            "security_id": "SEC-US-VOO",
            "source_record_id": "record-1",
            "observed_at_utc": "2026-08-03T19:00:00Z",
            "retrieved_at_utc": "2026-08-03T19:05:00Z",
            "captured_at_utc": "2026-08-03T19:06:00Z",
            "content_sha256": sha256_bytes(b"fixture"),
            "byte_count": 7,
            "storage_path": "data/raw/provider/raw_price/SEC-US-VOO.json",
            "capture_state": "CAPTURED",
        }

    def validate(self, manifest: dict, **kwargs) -> None:
        validate_capture_manifest(
            manifest,
            known_provider_ids=self.provider_ids,
            known_domains=self.domains,
            known_security_ids=self.security_ids,
            now_utc=NOW,
            **kwargs,
        )

    def test_raw_capture_policy_is_fail_closed(self) -> None:
        validate_capture_policy(self.policy)
        self.assertTrue(self.policy["raw_payloads_must_remain_outside_git"])
        self.assertFalse(self.policy["certified_market_monitoring_authorized"])

    def test_valid_capture_manifest_passes(self) -> None:
        self.validate(self.manifest)

    def test_duplicate_content_hash_is_rejected(self) -> None:
        with self.assertRaises(RawCaptureError):
            self.validate(self.manifest, existing_hashes={self.manifest["content_sha256"]})

    def test_future_observation_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["observed_at_utc"] = "2026-08-04T00:00:00Z"
        with self.assertRaises(RawCaptureError):
            self.validate(manifest)

    def test_retrieval_before_observation_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["retrieved_at_utc"] = "2026-08-03T18:59:00Z"
        with self.assertRaises(RawCaptureError):
            self.validate(manifest)

    def test_unknown_provider_domain_and_security_are_rejected(self) -> None:
        for field, value in (
            ("provider_id", "UNKNOWN"),
            ("data_domain", "UNKNOWN"),
            ("security_id", "VOO"),
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest[field] = value
            with self.assertRaises(RawCaptureError):
                self.validate(manifest)

    def test_storage_zone_matches_capture_state(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["storage_path"] = "data/quarantine/provider/raw_price/file.json"
        with self.assertRaises(RawCaptureError):
            self.validate(manifest)
        manifest["capture_state"] = "QUARANTINED"
        self.validate(manifest)

    def test_schema_and_git_boundaries_exist(self) -> None:
        schema = json.loads((ROOT / "contracts/native/raw_capture_manifest.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/raw/", ignore)
        self.assertIn(".env", ignore)


if __name__ == "__main__":
    unittest.main()
