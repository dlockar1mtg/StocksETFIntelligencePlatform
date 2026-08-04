from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from foundation.validation.security_master import (
    SecurityMasterValidationError,
    eligible_security_ids,
    validate_universe_policy,
)

ROOT = Path(__file__).resolve().parents[2]


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


class Phase161DynamicUniverseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_json("config/universe/etf_universe_policy.json")
        self.master = load_json("config/security/security_master.json")
        self.lock = load_json("config/governance/phase_1_governance_lock.json")

    def test_policy_is_layered_dynamic_and_fail_closed(self) -> None:
        validate_universe_policy(self.policy)
        self.assertEqual(self.policy["universe_id"], "US-ETF-DYNAMIC")
        self.assertTrue(self.policy["fail_closed"])

    def test_seed_etfs_are_required_but_not_the_universe_ceiling(self) -> None:
        self.assertEqual(
            self.policy["seed_security_ids"],
            ["SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"],
        )
        self.assertTrue(self.policy["universe_expansion_requires_certification"])
        self.assertNotIn("security_ids", self.policy)

    def test_all_required_universe_states_exist(self) -> None:
        required = {
            "DISCOVERED", "BROKER_ELIGIBLE", "ANALYTICS_PROVISIONAL",
            "ANALYTICS_ELIGIBLE", "PORTFOLIO_CANDIDATE", "SPECIALIZED",
            "PORTFOLIO_RESTRICTED", "BLOCKED",
        }
        self.assertEqual(set(self.policy["allowed_universe_states"]), required)

    def test_unknown_broker_status_cannot_be_eligible(self) -> None:
        self.assertTrue(self.policy["unknown_broker_status_blocked"])
        self.assertFalse(
            self.policy["admission_requirements"]["broker_status_unknown_is_eligible"]
        )

    def test_listing_and_broker_evidence_are_mandatory(self) -> None:
        requirements = self.policy["admission_requirements"]
        self.assertTrue(requirements["authoritative_listing_evidence"])
        self.assertTrue(requirements["broker_eligibility_evidence"])
        self.assertTrue(requirements["broker_verification_timestamp"])

    def test_ticker_only_identity_and_hard_coding_are_blocked(self) -> None:
        requirements = self.policy["admission_requirements"]
        self.assertFalse(requirements["ticker_as_sole_identifier_allowed"])
        self.assertTrue(self.policy["analytics_engine_must_not_hard_code_tickers"])

    def test_valid_additional_etf_is_not_rejected_by_seed_ceiling(self) -> None:
        expanded = copy.deepcopy(self.master)
        added = copy.deepcopy(expanded["securities"][0])
        added["security_id"] = "SEC-US-EXPANDED"
        added["ticker"] = "EXPANDED"
        added["share_class_id"] = "SHARE-US-EXPANDED"
        expanded["securities"].append(added)
        self.assertIn("SEC-US-EXPANDED", eligible_security_ids(expanded, self.policy))

    def test_weakened_admission_requirement_is_rejected(self) -> None:
        weakened = copy.deepcopy(self.policy)
        weakened["admission_requirements"]["broker_eligibility_evidence"] = False
        with self.assertRaises(SecurityMasterValidationError):
            validate_universe_policy(weakened)

    def test_dynamic_universe_does_not_grant_production_authority(self) -> None:
        authority = self.lock["phase_1_authority"]
        self.assertTrue(authority["universe_expansion_development"])
        for key in (
            "certified_market_monitoring", "certified_analytics",
            "certified_forecasts", "certified_recommendations",
            "certified_contribution_allocation", "certified_uip_export",
            "automatic_execution",
        ):
            self.assertFalse(authority[key], key)


if __name__ == "__main__":
    unittest.main()
