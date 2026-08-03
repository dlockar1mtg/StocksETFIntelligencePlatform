import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.validation.provider_contracts import (
    ProviderContractError,
    validate_observation,
    validate_phase_1_1,
    validate_provider_control,
)

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "config" / "providers" / "provider_contracts.json"


class Phase11ProviderContractTests(unittest.TestCase):
    def setUp(self):
        self.control = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
        self.observation = {
            "provider_id": "TEST_PROVIDER",
            "provider_version": "1.0.0",
            "source_tier": 3,
            "license_class": "PUBLIC_RESEARCH",
            "supported_domains": ["raw_price"],
            "security_id": "SEC-US-VOO",
            "domain": "raw_price",
            "source_record_id": "record-1",
            "observed_at_utc": "2026-08-01T20:00:00Z",
            "retrieved_at_utc": "2026-08-01T20:05:00Z",
            "as_of_date": "2026-08-01",
            "content_sha256": "a" * 64,
            "quality_status": "PROVISIONAL",
            "freshness_state": "CURRENT",
            "payload": {"close": 100.0},
        }
        self.now = datetime(2026, 8, 3, tzinfo=timezone.utc)

    def test_phase_1_1_control_passes(self):
        self.assertEqual(validate_phase_1_1(ROOT)["phase"], "1.1")

    def test_all_governed_data_domains_are_required(self):
        self.assertEqual(len(self.control["governed_domains"]), 10)
        validate_provider_control(self.control)

    def test_valid_observation_passes(self):
        validate_observation(self.control, self.observation, now=self.now)

    def test_missing_lineage_field_is_blocked(self):
        observation = copy.deepcopy(self.observation)
        del observation["content_sha256"]
        with self.assertRaises(ProviderContractError):
            validate_observation(self.control, observation, now=self.now)

    def test_ticker_only_identity_is_blocked(self):
        observation = copy.deepcopy(self.observation)
        observation["security_id"] = "VOO"
        with self.assertRaises(ProviderContractError):
            validate_observation(self.control, observation, now=self.now)

    def test_future_observation_is_blocked(self):
        observation = copy.deepcopy(self.observation)
        observation["observed_at_utc"] = "2026-08-04T00:00:00Z"
        observation["retrieved_at_utc"] = "2026-08-04T00:01:00Z"
        with self.assertRaises(ProviderContractError):
            validate_observation(self.control, observation, now=self.now)

    def test_unknown_domain_is_blocked(self):
        observation = copy.deepcopy(self.observation)
        observation["domain"] = "recommendation"
        with self.assertRaises(ProviderContractError):
            validate_observation(self.control, observation, now=self.now)

    def test_phase_1_authority_cannot_expand(self):
        weakened = copy.deepcopy(self.control)
        weakened["certified_analytics_authorized"] = True
        with self.assertRaises(ProviderContractError):
            validate_provider_control(weakened)


if __name__ == "__main__":
    unittest.main()
