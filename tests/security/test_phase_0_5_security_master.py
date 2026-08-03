from __future__ import annotations

import copy
import unittest
from pathlib import Path

from foundation.validation.security_master import (
    SecurityMasterValidationError,
    eligible_security_ids,
    load_json,
    validate_registries,
    validate_security_master,
    validate_universe_policy,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase05SecurityMasterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.master = load_json(ROOT / "config/security/security_master.json")
        self.issuer_funds = load_json(ROOT / "config/security/issuer_fund_registry.json")
        self.benchmarks = load_json(ROOT / "config/security/benchmark_registry.json")
        self.policy = load_json(ROOT / "config/universe/etf_universe_policy.json")

    def test_security_master_is_fail_closed(self) -> None:
        validate_security_master(self.master)
        self.assertTrue(self.master["unknown_security_blocked"])
        self.assertTrue(self.master["ticker_only_identity_blocked"])

    def test_required_seed_security_ids_are_present(self) -> None:
        governed = {item["security_id"] for item in self.master["securities"]}
        self.assertTrue(set(self.policy["seed_security_ids"]).issubset(governed))

    def test_every_security_has_complete_identity(self) -> None:
        validate_security_master(self.master)
        for item in self.master["securities"]:
            self.assertTrue(item["issuer_id"])
            self.assertTrue(item["fund_id"])
            self.assertTrue(item["share_class_id"])
            self.assertTrue(item["benchmark_id"])

    def test_registry_relationships_are_valid(self) -> None:
        validate_registries(self.master, self.issuer_funds, self.benchmarks)

    def test_unknown_benchmark_is_rejected(self) -> None:
        broken = copy.deepcopy(self.master)
        broken["securities"][0]["benchmark_id"] = "IDX-UNKNOWN"
        with self.assertRaises(SecurityMasterValidationError):
            validate_registries(broken, self.issuer_funds, self.benchmarks)

    def test_ticker_only_identity_is_rejected(self) -> None:
        broken = copy.deepcopy(self.master)
        broken["securities"][0]["security_id"] = "VOO"
        with self.assertRaises(SecurityMasterValidationError):
            validate_security_master(broken)

    def test_universe_policy_is_dynamic_and_fail_closed(self) -> None:
        validate_universe_policy(self.policy)
        self.assertEqual(self.policy["universe_id"], "US-ETF-DYNAMIC")
        self.assertTrue(self.policy["universe_expansion_requires_certification"])
        self.assertTrue(self.policy["seed_securities_must_remain_present"])
        self.assertFalse(self.policy["individual_stock_production_authorized"])

    def test_current_seed_universe_is_eligible(self) -> None:
        self.assertEqual(
            eligible_security_ids(self.master, self.policy),
            ["SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"],
        )

    def test_additional_valid_etf_can_become_eligible(self) -> None:
        expanded = copy.deepcopy(self.master)
        added = copy.deepcopy(expanded["securities"][0])
        added["security_id"] = "SEC-US-TESTETF"
        added["ticker"] = "TESTETF"
        added["share_class_id"] = "SHARE-US-TESTETF"
        expanded["securities"].append(added)
        self.assertIn("SEC-US-TESTETF", eligible_security_ids(expanded, self.policy))

    def test_missing_or_inactive_seed_is_rejected(self) -> None:
        missing = copy.deepcopy(self.master)
        missing["securities"] = missing["securities"][1:]
        with self.assertRaises(SecurityMasterValidationError):
            eligible_security_ids(missing, self.policy)

        inactive = copy.deepcopy(self.master)
        inactive["securities"][0]["lifecycle_status"] = "DELISTED"
        with self.assertRaises(SecurityMasterValidationError):
            eligible_security_ids(inactive, self.policy)


if __name__ == "__main__":
    unittest.main()
