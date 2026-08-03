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

    def test_exact_governed_security_ids(self) -> None:
        self.assertEqual(
            [item["security_id"] for item in self.master["securities"]],
            ["SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"],
        )

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

    def test_universe_eligibility_is_exact(self) -> None:
        self.assertEqual(
            eligible_security_ids(self.master, self.policy),
            ["SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"],
        )
        self.assertFalse(self.policy["individual_stock_production_authorized"])

    def test_inactive_or_unknown_security_is_ineligible(self) -> None:
        inactive = copy.deepcopy(self.master)
        inactive["securities"][0]["lifecycle_status"] = "DELISTED"
        with self.assertRaises(SecurityMasterValidationError):
            eligible_security_ids(inactive, self.policy)
        unknown_policy = copy.deepcopy(self.policy)
        unknown_policy["security_ids"].append("SEC-US-UNKNOWN")
        with self.assertRaises(SecurityMasterValidationError):
            eligible_security_ids(self.master, unknown_policy)


if __name__ == "__main__":
    unittest.main()
