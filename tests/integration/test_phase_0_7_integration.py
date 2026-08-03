from __future__ import annotations

import copy
import unittest
from pathlib import Path

from foundation.validation.phase_0_integration import (
    Phase0IntegrationError,
    load_json,
    validate_completion_control,
    validate_cross_control_consistency,
    validate_phase_0,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase07IntegrationTests(unittest.TestCase):
    def test_phase_0_integration_passes(self) -> None:
        control = validate_phase_0(ROOT)
        self.assertTrue(control["fail_closed"])

    def test_all_subphases_are_required(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        self.assertEqual(control["required_subphases"], ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7"])

    def test_all_required_control_files_exist(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        validate_completion_control(ROOT, control)
        self.assertGreaterEqual(len(control["required_control_files"]), 12)

    def test_phase_0_grants_no_production_authority(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        self.assertFalse(control["production_authority_granted"])
        self.assertFalse(control["automatic_execution_authorized"])
        self.assertFalse(control["direct_uip_database_writes_authorized"])
        self.assertFalse(control["individual_stock_production_authorized"])

    def test_tier_1_identity_is_consistent_across_controls(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        validate_cross_control_consistency(ROOT, control)
        self.assertEqual(control["tier_1_security_ids"], ["SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"])

    def test_weakened_test_floor_is_rejected(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        weakened = copy.deepcopy(control)
        weakened["minimum_regression_tests"] = 55
        with self.assertRaises(Phase0IntegrationError):
            validate_completion_control(ROOT, weakened)

    def test_missing_subphase_is_rejected(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        weakened = copy.deepcopy(control)
        weakened["required_subphases"] = weakened["required_subphases"][:-1]
        with self.assertRaises(Phase0IntegrationError):
            validate_completion_control(ROOT, weakened)

    def test_authority_expansion_is_rejected(self) -> None:
        control = load_json(ROOT / "config/certification/phase_0_completion.json")
        weakened = copy.deepcopy(control)
        weakened["production_authority_granted"] = True
        with self.assertRaises(Phase0IntegrationError):
            validate_completion_control(ROOT, weakened)


if __name__ == "__main__":
    unittest.main()
