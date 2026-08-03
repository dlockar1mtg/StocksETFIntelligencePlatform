from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from foundation.validation.phase_1_integration import Phase1IntegrationError, validate_phase_1

ROOT = Path(__file__).resolve().parents[2]


class Phase15IntegrationTests(unittest.TestCase):
    def test_integrated_phase_1_passes(self) -> None:
        result = validate_phase_1(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["minimum_tests_required"], 106)

    def test_all_subphases_are_required(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_completion.json").read_text(encoding="utf-8"))
        self.assertEqual(control["required_subphases"], ["1.1", "1.2", "1.3", "1.4", "1.5"])

    def test_all_required_control_files_exist(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_completion.json").read_text(encoding="utf-8"))
        for relative in control["required_control_files"]:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_security_and_domain_identity_are_consistent(self) -> None:
        result = validate_phase_1(ROOT)
        self.assertEqual(result["security_ids"], ["SEC-US-QQQM", "SEC-US-SCHD", "SEC-US-VOO"])
        self.assertEqual(len(result["governed_domains"]), 10)

    def test_weakened_test_floor_is_rejected(self) -> None:
        original = json.loads((ROOT / "config/certification/phase_1_completion.json").read_text(encoding="utf-8"))
        weakened = copy.deepcopy(original)
        weakened["minimum_tests_required"] = 105
        with patch("foundation.validation.phase_1_integration.load_json") as mocked:
            mocked.side_effect = lambda path: weakened if path.name == "phase_1_completion.json" else json.loads(path.read_text(encoding="utf-8-sig"))
            with self.assertRaises(Phase1IntegrationError):
                validate_phase_1(ROOT)

    def test_authority_expansion_is_rejected(self) -> None:
        original = json.loads((ROOT / "config/certification/phase_1_completion.json").read_text(encoding="utf-8"))
        expanded = copy.deepcopy(original)
        expanded["certified_analytics_authorized"] = True
        with patch("foundation.validation.phase_1_integration.load_json") as mocked:
            mocked.side_effect = lambda path: expanded if path.name == "phase_1_completion.json" else json.loads(path.read_text(encoding="utf-8-sig"))
            with self.assertRaises(Phase1IntegrationError):
                validate_phase_1(ROOT)

    def test_missing_evidence_and_conflict_protections_are_locked(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_completion.json").read_text(encoding="utf-8"))
        self.assertTrue(control["missing_evidence_reduces_confidence"])
        self.assertTrue(control["silent_imputation_forbidden"])
        self.assertTrue(control["critical_conflicts_require_quarantine"])
        self.assertTrue(control["look_ahead_forbidden"])

    def test_phase_1_grants_no_production_authority(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_completion.json").read_text(encoding="utf-8"))
        for key in (
            "certified_market_monitoring_authorized",
            "certified_analytics_authorized",
            "certified_recommendations_authorized",
            "certified_uip_export_authorized",
            "automatic_execution_authorized",
            "direct_uip_database_writes_authorized",
        ):
            self.assertFalse(control[key], key)


if __name__ == "__main__":
    unittest.main()
