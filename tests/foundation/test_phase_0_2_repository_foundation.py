from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = json.loads((ROOT / "config/architecture/repository_layers.json").read_text(encoding="utf-8-sig"))
GOV = json.loads((ROOT / "config/governance/governance_manifest.json").read_text(encoding="utf-8-sig"))


class Phase02RepositoryFoundationTests(unittest.TestCase):
    def test_python_project_configuration_exists(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8-sig")
        self.assertIn('requires-python = ">=3.11"', text)
        self.assertIn('include = ["foundation*"]', text)

    def test_required_architecture_paths_are_declared(self) -> None:
        self.assertEqual(len(ARCH["required_top_level_paths"]), 10)
        self.assertIn("exports", ARCH["required_top_level_paths"])
        self.assertIn("contracts", ARCH["required_top_level_paths"])

    def test_all_foundation_layers_are_declared(self) -> None:
        self.assertEqual(
            ARCH["foundation_layers"],
            ["domain", "infrastructure", "applications", "validation", "integration"],
        )

    def test_domain_layer_has_no_forbidden_imports(self) -> None:
        domain = ROOT / "foundation" / "domain"
        text = "\n".join(p.read_text(encoding="utf-8-sig") for p in domain.rglob("*.py"))
        for forbidden in ARCH["domain_forbidden_dependencies"]:
            self.assertNotIn(f"import {forbidden}", text)
            self.assertNotIn(f"from {forbidden}", text)

    def test_governance_remains_fail_closed(self) -> None:
        self.assertFalse(GOV["automatic_execution_authorized"])
        self.assertFalse(GOV["direct_uip_database_writes_authorized"])
        self.assertFalse(GOV["certified_recommendations_authorized"])
        self.assertFalse(GOV["certified_uip_export_authorized"])

    def test_architecture_cannot_expand_authority(self) -> None:
        self.assertFalse(ARCH["research_may_authorize_production"])
        self.assertFalse(ARCH["direct_uip_database_writes_authorized"])
        self.assertFalse(ARCH["automatic_execution_authorized"])

    def test_environment_validator_exists(self) -> None:
        self.assertTrue((ROOT / "scripts" / "validate_environment.py").is_file())

    def test_phase_0_1_regression_suite_is_preserved(self) -> None:
        self.assertTrue((ROOT / "tests" / "governance" / "test_phase_0_1_regression.py").is_file())


if __name__ == "__main__":
    unittest.main()
