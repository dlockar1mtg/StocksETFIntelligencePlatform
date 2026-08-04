import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "config" / "governance"
STANDARD = ROOT / "docs" / "standards" / "ETF_ANALYTICAL_STANDARD.md"
UNIVERSE = ROOT / "config" / "universe" / "etf_universe_policy.json"


def load_json(name: str):
    return json.loads((GOVERNANCE / name).read_text(encoding="utf-8-sig"))


class Phase1GovernanceLockTests(unittest.TestCase):
    def setUp(self):
        self.lock = load_json("phase_1_governance_lock.json")
        self.manifest = load_json("governance_manifest.json")
        self.authority = load_json("certification_authority.json")
        self.prohibited = load_json("prohibited_actions.json")
        self.universe = json.loads(UNIVERSE.read_text(encoding="utf-8-sig"))
        self.standard = STANDARD.read_text(encoding="utf-8-sig")

    def test_phase_and_governing_authority_are_exact(self):
        self.assertEqual(self.lock["phase"], "1")
        self.assertEqual(self.authority["current_phase"], "1")
        self.assertTrue(self.authority["phase_0_certified"])
        self.assertEqual(self.lock["governing_repository"], "dlockar1mtg/UniversalInvestmentPlatform")
        self.assertEqual(self.lock["governing_issue_number"], 32)

    def test_seed_universe_is_required_but_not_a_fixed_ceiling(self):
        expected_tickers = ["VOO", "SCHD", "QQQM"]
        expected_ids = ["SEC-US-VOO", "SEC-US-SCHD", "SEC-US-QQQM"]
        self.assertEqual(self.lock["seed_tickers"], expected_tickers)
        self.assertEqual(self.lock["seed_security_ids"], expected_ids)
        self.assertEqual(self.universe["seed_security_ids"], expected_ids)
        self.assertEqual(self.manifest["initial_asset_scope"], expected_tickers)
        self.assertEqual(self.lock["universe_model"], "LAYERED_DYNAMIC_ETF_UNIVERSE")
        self.assertTrue(self.lock["universe_expansion_requires_governed_identity"])

    def test_all_universe_layers_are_governed(self):
        required = {
            "DISCOVERY", "BROKER_ELIGIBLE", "ANALYTICS_ELIGIBLE",
            "PORTFOLIO_CANDIDATE", "SPECIALIZED_OR_RESTRICTED",
        }
        self.assertEqual(set(self.lock["required_universe_layers"]), required)
        self.assertFalse(self.lock["unknown_broker_status_is_eligible"])
        self.assertTrue(self.lock["universe_expansion_requires_listing_evidence"])
        self.assertTrue(self.lock["universe_expansion_requires_broker_evidence"])

    def test_all_seven_etf_pillars_remain_locked(self):
        pillars = self.lock["required_etf_pillars"]
        self.assertEqual(len(pillars), 7)
        for pillar in pillars:
            self.assertIn(pillar, self.standard)

    def test_phase_1_data_domains_cover_governing_issue_and_standard(self):
        required = {
            "raw_prices", "provider_adjusted_prices", "distributions",
            "splits_and_material_corporate_actions", "etf_metadata", "holdings",
            "expense_ratios", "assets_under_management", "liquidity",
            "strategy_benchmarks", "common_equity_benchmark", "cash_hurdle",
        }
        self.assertTrue(required.issubset(set(self.lock["phase_1_required_data_domains"])))

    def test_lineage_and_point_in_time_fields_are_mandatory(self):
        required = {
            "security_id", "source_id", "source_tier", "source_record_id",
            "observed_at_utc", "ingested_at_utc", "as_of_date", "content_sha256",
            "data_quality_status", "freshness_status",
        }
        self.assertTrue(required.issubset(set(self.lock["required_evidence_fields"])))

    def test_missing_evidence_cannot_be_silently_imputed_or_rewarded(self):
        behavior = self.lock["required_behaviors"]
        self.assertFalse(behavior["missing_evidence_silently_imputed"])
        self.assertFalse(behavior["missing_evidence_rewarded"])
        self.assertIn("must not be silently imputed or rewarded", self.standard)

    def test_return_reconciliation_and_corporate_actions_remain_required(self):
        behavior = self.lock["required_behaviors"]
        self.assertTrue(behavior["raw_evidence_preserved"])
        self.assertTrue(behavior["provider_adjusted_and_reconstructed_total_returns_reconciled"])
        self.assertIn("Raw prices, distributions, splits, and material corporate actions must be preserved", self.standard)

    def test_conflicts_are_preserved_and_quarantined(self):
        behavior = self.lock["required_behaviors"]
        self.assertTrue(behavior["source_conflicts_preserved"])
        self.assertTrue(behavior["conflicts_quarantined"])
        self.assertIn("silent_decision_critical_source_conflict", self.prohibited["prohibited_actions"])

    def test_phase_1_does_not_expand_decision_or_execution_authority(self):
        authority = self.lock["phase_1_authority"]
        self.assertTrue(authority["universe_expansion_development"])
        for key in (
            "certified_market_monitoring", "certified_analytics", "certified_forecasts",
            "certified_recommendations", "certified_contribution_allocation",
            "certified_uip_export", "automatic_execution",
        ):
            self.assertFalse(authority[key], key)
        for key in ("market_monitoring", "asset_outlook", "portfolio_action", "contribution_allocation", "uip_export", "automatic_execution"):
            self.assertFalse(self.authority["authorized"][key], key)

    def test_critical_repository_boundaries_remain_fail_closed(self):
        behavior = self.lock["required_behaviors"]
        self.assertFalse(behavior["look_ahead_allowed"])
        self.assertFalse(behavior["ticker_as_sole_permanent_identifier_allowed"])
        self.assertFalse(behavior["direct_uip_database_writes_allowed"])
        self.assertFalse(behavior["raw_data_committed_to_git"])
        self.assertFalse(behavior["generated_packages_committed_to_git"])
        self.assertFalse(behavior["secrets_committed_to_git"])
        self.assertTrue(self.lock["fail_closed"])
        self.assertTrue(self.authority["critical_failures_block_authority"])
        self.assertTrue(self.authority["owner_approval_cannot_override_critical_failure"])


if __name__ == "__main__":
    unittest.main()
