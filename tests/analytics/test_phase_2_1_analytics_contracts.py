from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from foundation.analytics.contracts import AnalyticsContractError, PILLARS, validate_metric_definition, validate_phase_2_1


ROOT = Path(__file__).resolve().parents[2]


class Phase21AnalyticsContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = json.loads((ROOT / "config/analytics/metric_catalog.json").read_text())
        self.lock = json.loads((ROOT / "config/governance/phase_2_analytics_lock.json").read_text())

    def test_phase_2_1_contracts_pass(self) -> None:
        result = validate_phase_2_1(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(set(result["pillars"]), PILLARS)

    def test_all_seven_pillars_are_locked(self) -> None:
        self.assertEqual(set(self.lock["required_etf_pillars"]), PILLARS)

    def test_catalog_covers_all_seven_pillars(self) -> None:
        self.assertEqual({m["pillar"] for m in self.catalog["metrics"]}, PILLARS)

    def test_metric_ids_are_unique(self) -> None:
        ids = [m["metric_id"] for m in self.catalog["metrics"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_three_year_horizon_is_primary(self) -> None:
        self.assertEqual(self.lock["primary_strategic_horizon"], "3Y")
        self.assertEqual(self.catalog["primary_strategic_horizon"], "3Y")

    def test_point_in_time_and_total_return_controls_are_required(self) -> None:
        controls = self.lock["required_calculation_controls"]
        self.assertTrue(controls["point_in_time_only"])
        self.assertTrue(controls["total_return_primary"])
        self.assertTrue(controls["provider_adjusted_and_reconstructed_returns_reconciled"])

    def test_look_ahead_survivorship_and_imputation_are_blocked(self) -> None:
        controls = self.lock["required_calculation_controls"]
        self.assertFalse(controls["look_ahead_allowed"])
        self.assertFalse(controls["survivorship_bias_allowed"])
        self.assertFalse(controls["silent_imputation_allowed"])
        self.assertFalse(controls["missing_evidence_rewarded"])

    def test_phase_2_1_grants_no_production_or_decision_authority(self) -> None:
        authority = self.lock["phase_2_1_authority"]
        for key in ("production_metric_calculation", "scoring", "ranking", "forecasting", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"):
            self.assertFalse(authority[key])

    def test_contract_is_registered(self) -> None:
        registry = json.loads((ROOT / "config/contracts/contract_registry.json").read_text())
        ids = {entry["contract_id"] for entry in registry["contracts"]}
        self.assertIn("native.analytics_metric_definition", ids)

    def test_invalid_metric_fields_fail_closed(self) -> None:
        metric = deepcopy(self.catalog["metrics"][0])
        metric["unexpected"] = True
        with self.assertRaises(AnalyticsContractError):
            validate_metric_definition(metric)

    def test_unknown_pillar_fails_closed(self) -> None:
        metric = deepcopy(self.catalog["metrics"][0])
        metric["pillar"] = "UNKNOWN"
        with self.assertRaises(AnalyticsContractError):
            validate_metric_definition(metric)

    def test_duplicate_domains_fail_closed(self) -> None:
        metric = deepcopy(self.catalog["metrics"][0])
        metric["required_domains"] = ["raw_prices", "raw_prices"]
        with self.assertRaises(AnalyticsContractError):
            validate_metric_definition(metric)

    def test_missing_catalog_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config/governance").mkdir(parents=True)
            (root / "config/contracts").mkdir(parents=True)
            (root / "config/governance/phase_2_analytics_lock.json").write_text(json.dumps(self.lock))
            (root / "config/contracts/contract_registry.json").write_text(json.dumps({"contracts": []}))
            with self.assertRaises((AnalyticsContractError, FileNotFoundError)):
                validate_phase_2_1(root)


if __name__ == "__main__":
    unittest.main()
