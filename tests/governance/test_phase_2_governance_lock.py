from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load(relative: str) -> dict:
    with (ROOT / relative).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


class Phase2GovernanceLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = load("config/governance/phase_2_governance_lock.json")
        cls.authority = load("config/governance/certification_authority.json")
        cls.security_master = load("config/security/security_master.json")
        cls.return_standard = load("config/market/return_standard.json")
        cls.corporate_actions = load("config/market/corporate_action_policy.json")

    def test_phase_and_prior_certifications_are_exact(self) -> None:
        self.assertEqual(self.lock["phase"], "2")
        self.assertEqual(self.authority["current_phase"], "2")
        self.assertTrue(self.authority["phase_0_certified"])
        self.assertTrue(self.authority["phase_1_certified"])
        self.assertEqual(self.lock["governing_repository"], "dlockar1mtg/UniversalInvestmentPlatform")
        self.assertEqual(self.lock["governing_issue_number"], 32)

    def test_initial_universe_remains_exact_and_stable(self) -> None:
        required = {"SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"}
        actual = {item["security_id"] for item in self.security_master["securities"]}
        self.assertEqual(set(self.lock["initial_security_ids"]), required)
        self.assertEqual(actual, required)

    def test_required_phase_2_analytics_are_complete(self) -> None:
        required = {
            "total_return", "dividend_return", "volatility", "drawdown",
            "beta", "correlation", "momentum", "trend",
            "etf_factor_exposure", "etf_holdings_exposure",
            "dividend_quality", "dividend_growth", "dividend_yield",
            "dividend_sustainability",
        }
        self.assertEqual(set(self.lock["required_analytics_domains"]), required)

    def test_total_return_and_corporate_action_controls_remain_locked(self) -> None:
        controls = self.lock["required_return_controls"]
        self.assertEqual(controls["security_return_basis"], "total_return")
        self.assertEqual(controls["benchmark_return_basis"], "total_return")
        self.assertTrue(controls["provider_adjusted_and_reconstructed_returns_reconciled"])
        self.assertTrue(controls["corporate_action_evidence_required"])
        self.assertTrue(controls["non_trading_day_returns_forbidden"])
        self.assertEqual(self.return_standard["security_return_basis"], "total_return")
        self.assertEqual(self.return_standard["benchmark_return_basis"], "total_return")
        self.assertTrue(self.corporate_actions["point_in_time_required"])

    def test_point_in_time_and_look_ahead_protections_remain_locked(self) -> None:
        controls = self.lock["required_point_in_time_controls"]
        self.assertFalse(controls["look_ahead_allowed"])
        self.assertTrue(controls["observation_and_availability_dates_required"])
        self.assertFalse(controls["future_effective_records_allowed"])
        self.assertFalse(controls["latest_revised_history_used_without_as_of_control"])

    def test_missing_stale_and_conflicted_evidence_fail_closed(self) -> None:
        controls = self.lock["required_evidence_controls"]
        self.assertTrue(controls["stable_security_identity_required"])
        self.assertTrue(controls["lineage_required"])
        self.assertTrue(controls["freshness_required"])
        self.assertFalse(controls["missing_evidence_silently_imputed"])
        self.assertFalse(controls["missing_evidence_rewarded"])
        self.assertFalse(controls["stale_evidence_supports_certified_analytics"])
        self.assertTrue(controls["critical_conflicts_quarantined"])

    def test_phase_2_development_authority_is_explicit(self) -> None:
        authority = self.authority["authorized"]
        for key in (
            "analytics_development", "return_analytics_development",
            "risk_analytics_development", "trend_analytics_development",
            "exposure_analytics_development", "income_analytics_development",
        ):
            self.assertTrue(authority[key], key)

    def test_forecasting_and_decision_authority_remain_blocked(self) -> None:
        authority = self.authority["authorized"]
        for key in (
            "market_monitoring", "asset_outlook", "forecasting",
            "recommendations", "portfolio_action", "contribution_allocation",
            "uip_export", "automatic_execution",
        ):
            self.assertFalse(authority[key], key)

    def test_domain_repository_boundaries_remain_blocked(self) -> None:
        authority = self.lock["phase_2_authority"]
        self.assertFalse(authority["certified_uip_export"])
        self.assertFalse(authority["automatic_execution"])
        self.assertFalse(authority["direct_uip_database_writes"])

    def test_phase_2_lock_is_fail_closed(self) -> None:
        self.assertTrue(self.lock["fail_closed"])
        self.assertTrue(self.authority["critical_failures_block_authority"])
        self.assertTrue(self.authority["owner_approval_cannot_override_critical_failure"])


if __name__ == "__main__":
    unittest.main()
