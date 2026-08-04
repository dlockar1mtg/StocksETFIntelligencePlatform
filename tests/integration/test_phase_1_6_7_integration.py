from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.validation.phase_1_6_7_integration import Phase167IntegrationError, validate_phase_1_6_7


ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "config/certification/phase_1_6_7_completion.json"
ATTESTATION_PATH = ROOT / "config/certification/phase_1_6_7_snapshot_attestation.json"


class Phase167IntegrationTests(unittest.TestCase):
    def _write_clean_checkout_controls(self, root: Path) -> None:
        destination = root / "config/certification"
        destination.mkdir(parents=True)
        (destination / CONTROL_PATH.name).write_text(CONTROL_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        (destination / ATTESTATION_PATH.name).write_text(ATTESTATION_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    def test_integrated_dynamic_universe_passes(self) -> None:
        result = validate_phase_1_6_7(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["counts"]["total_records"], 5535)
        self.assertEqual(result["counts"]["broker_eligible"], 5530)
        self.assertIn(result["snapshot_evidence_mode"], {"ATTESTATION_ONLY", "LOCAL_SNAPSHOT_VERIFIED"})

    def test_snapshot_hash_is_locked(self) -> None:
        control = json.loads(CONTROL_PATH.read_text())
        attestation = json.loads(ATTESTATION_PATH.read_text())
        expected = "28d3f083521cb2bbbdd8fe6acf92c5c99eadd52a1180505e8b4ca7c0cadf0e32"
        self.assertEqual(control["snapshot_sha256"], expected)
        self.assertEqual(attestation["snapshot_sha256"], expected)
        self.assertTrue(control["snapshot_must_be_immutable"])

    def test_full_snapshot_replaces_structural_baseline(self) -> None:
        result = validate_phase_1_6_7(ROOT)
        self.assertGreater(result["counts"]["total_records"], 3)
        self.assertEqual(result["counts"]["total_records"], 5535)

    def test_blocked_symbol_set_is_exact(self) -> None:
        result = validate_phase_1_6_7(ROOT)
        self.assertEqual(result["blocked_symbols"], ["IPB", "JULP", "MARW", "NVIR", "SDEM"])

    def test_all_dynamic_universe_subphases_are_required(self) -> None:
        control = json.loads(CONTROL_PATH.read_text())
        for phase in ("1.6.1", "1.6.2", "1.6.3", "1.6.4", "1.6.5", "1.6.6", "1.6.6a", "1.6.6b", "1.6.6c", "1.6.7"):
            self.assertIn(phase, control["required_subphases"])

    def test_downstream_authority_remains_false(self) -> None:
        control = json.loads(CONTROL_PATH.read_text())
        attestation = json.loads(ATTESTATION_PATH.read_text())
        authority_keys = [key for key in control if key.endswith("_authorized")]
        self.assertGreaterEqual(len(authority_keys), 7)
        self.assertTrue(all(control[key] is False for key in authority_keys))
        for key in ("recommendation_authority", "analytics_authority", "portfolio_authority", "execution_authority", "direct_uip_database_write_authority"):
            self.assertIs(attestation[key], False)

    def test_test_floor_cannot_be_weakened(self) -> None:
        control = json.loads(CONTROL_PATH.read_text())
        self.assertGreaterEqual(control["minimum_tests_required"], 209)

    def test_clean_checkout_uses_attestation_without_generated_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_clean_checkout_controls(root)
            result = validate_phase_1_6_7(root)
            self.assertEqual(result["snapshot_evidence_mode"], "ATTESTATION_ONLY")
            self.assertEqual(result["counts"]["total_records"], 5535)

    def test_missing_attestation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "config/certification"
            destination.mkdir(parents=True)
            (destination / CONTROL_PATH.name).write_text(CONTROL_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaises(Phase167IntegrationError):
                validate_phase_1_6_7(root)

    def test_local_snapshot_if_present_must_match_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_clean_checkout_controls(root)
            snapshot_path = root / "data/certified/2026-08-03/robinhood_full_universe_snapshot.json"
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_text('{"tampered": true}\n', encoding="utf-8")
            with self.assertRaisesRegex(Phase167IntegrationError, "hash drift"):
                validate_phase_1_6_7(root)


if __name__ == "__main__":
    unittest.main()
