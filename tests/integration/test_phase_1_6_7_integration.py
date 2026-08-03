from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.validation.phase_1_6_7_integration import Phase167IntegrationError, validate_phase_1_6_7


ROOT = Path(__file__).resolve().parents[2]


class Phase167IntegrationTests(unittest.TestCase):
    def test_integrated_dynamic_universe_passes(self) -> None:
        result = validate_phase_1_6_7(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["counts"]["total_records"], 5535)
        self.assertEqual(result["counts"]["broker_eligible"], 5530)

    def test_snapshot_hash_is_locked(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_6_7_completion.json").read_text())
        self.assertEqual(control["snapshot_sha256"], "28d3f083521cb2bbbdd8fe6acf92c5c99eadd52a1180505e8b4ca7c0cadf0e32")
        self.assertTrue(control["snapshot_must_be_immutable"])

    def test_full_snapshot_replaces_structural_baseline(self) -> None:
        result = validate_phase_1_6_7(ROOT)
        self.assertGreater(result["counts"]["total_records"], 3)
        self.assertEqual(result["counts"]["total_records"], 5535)

    def test_blocked_symbol_set_is_exact(self) -> None:
        result = validate_phase_1_6_7(ROOT)
        self.assertEqual(result["blocked_symbols"], ["IPB", "JULP", "MARW", "NVIR", "SDEM"])

    def test_all_dynamic_universe_subphases_are_required(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_6_7_completion.json").read_text())
        for phase in ("1.6.1", "1.6.2", "1.6.3", "1.6.4", "1.6.5", "1.6.6", "1.6.6a", "1.6.6b", "1.6.6c", "1.6.7"):
            self.assertIn(phase, control["required_subphases"])

    def test_downstream_authority_remains_false(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_6_7_completion.json").read_text())
        authority_keys = [key for key in control if key.endswith("_authorized")]
        self.assertGreaterEqual(len(authority_keys), 7)
        self.assertTrue(all(control[key] is False for key in authority_keys))

    def test_test_floor_cannot_be_weakened(self) -> None:
        control = json.loads((ROOT / "config/certification/phase_1_6_7_completion.json").read_text())
        self.assertGreaterEqual(control["minimum_tests_required"], 207)

    def test_missing_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config/certification").mkdir(parents=True)
            control = json.loads((ROOT / "config/certification/phase_1_6_7_completion.json").read_text())
            (root / "config/certification/phase_1_6_7_completion.json").write_text(json.dumps(control), encoding="utf-8")
            with self.assertRaises(Phase167IntegrationError):
                validate_phase_1_6_7(root)


if __name__ == "__main__":
    unittest.main()
