import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "governance"
DOCS = ROOT / "docs"


def load_json(name: str):
    return json.loads((CONFIG / name).read_text(encoding="utf-8-sig"))


class Phase01GovernanceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_json("governance_manifest.json")
        self.register = load_json("decision_register.json")
        self.prohibited = load_json("prohibited_actions.json")
        self.authority = load_json("certification_authority.json")
        self.etf_standard = (DOCS / "standards" / "ETF_ANALYTICAL_STANDARD.md").read_text(encoding="utf-8-sig")

    def test_exact_initial_etf_scope(self):
        self.assertEqual(self.manifest["initial_asset_scope"], ["VOO", "SCHD", "QQQM"])

    def test_all_sixteen_decisions_are_option_c(self):
        decisions = self.register["decisions"]
        self.assertEqual(len(decisions), 16)
        self.assertEqual([d["id"] for d in decisions], list(range(1, 17)))
        self.assertTrue(all(d["approved_option"] == "C" for d in decisions))
        self.assertEqual(self.manifest["required_governance_decision_count"], 16)
        self.assertEqual(set(self.manifest["approved_decision_options"].values()), {"C"})

    def test_governing_issue_identity(self):
        self.assertEqual(self.manifest["governing_repository"], "dlockar1mtg/UniversalInvestmentPlatform")
        self.assertEqual(self.manifest["governing_issue_number"], 32)
        self.assertEqual(self.register["governing_issue_number"], 32)

    def test_phase_zero_has_no_decision_authority(self):
        self.assertFalse(self.manifest["automatic_execution_authorized"])
        self.assertFalse(self.manifest["direct_uip_database_writes_authorized"])
        self.assertFalse(self.manifest["certified_recommendations_authorized"])
        self.assertFalse(self.manifest["certified_contribution_allocation_authorized"])
        self.assertFalse(self.manifest["certified_uip_export_authorized"])
        for key in ("market_monitoring", "asset_outlook", "portfolio_action", "contribution_allocation", "uip_export", "automatic_execution"):
            self.assertFalse(self.authority["authorized"][key], key)

    def test_critical_prohibitions_exist(self):
        actions = set(self.prohibited["prohibited_actions"])
        required = {
            "automatic_trade_execution",
            "direct_uip_production_database_write",
            "research_output_claiming_certified_authority",
            "look_ahead_information_in_historical_validation",
            "individual_stock_production_without_separate_approval",
        }
        self.assertTrue(required.issubset(actions))

    def test_certification_fails_closed(self):
        self.assertTrue(self.authority["critical_failures_block_authority"])
        self.assertTrue(self.authority["owner_approval_cannot_override_critical_failure"])

    def test_etf_standard_contains_all_pillars(self):
        required = [
            "Return and trend",
            "Risk and drawdown",
            "Valuation and underlying fundamentals",
            "Income and distributions",
            "Fund structure and implementation quality",
            "Diversification, concentration, and overlap",
            "Regime and portfolio fit",
        ]
        for phrase in required:
            self.assertIn(phrase, self.etf_standard)

    def test_forecast_horizon_governance(self):
        self.assertEqual(self.manifest["primary_strategic_horizon"], "3Y")
        for phrase in ("1 month", "3 months", "1 year", "3 years", "5 years"):
            self.assertIn(phrase, self.etf_standard)


if __name__ == "__main__":
    unittest.main()
