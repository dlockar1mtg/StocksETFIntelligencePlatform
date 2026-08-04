import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foundation.universe.analytics_eligibility import evaluate_analytics_eligibility, validate_snapshot, AnalyticsEligibilityError

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/universe/analytics_eligibility_policy.json").read_text())


def valid_record():
    coverage = {d: {"present": True, "freshness_status": "CURRENT"} for d in POLICY["required_core_domains"]}
    return {
        "security_id": "SEC-US-VOO",
        "evaluated_at_utc": "2026-08-03T20:00:00+00:00",
        "prior_states": ["DISCOVERED", "BROKER_ELIGIBLE"],
        "domain_coverage": coverage,
        "price_history_trading_days": 756,
        "critical_conflict": False,
        "quality_status": "PASS",
        "evidence_lineage_complete": True,
        "point_in_time_complete": True,
        "specialized_product_type": "NONE",
        "strategy_specific_coverage_complete": True,
    }


class Phase165AnalyticsEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 3, 21, 0, tzinfo=timezone.utc)

    def test_policy_is_fail_closed(self):
        self.assertTrue(POLICY["fail_closed"])
        self.assertFalse(POLICY["silent_imputation_allowed"])
        self.assertFalse(POLICY["missing_evidence_rewarded"])

    def test_contract_is_registered(self):
        registry = json.loads((ROOT / "config/contracts/contract_registry.json").read_text())
        self.assertIn("native.analytics_eligibility_record", {c["contract_id"] for c in registry["contracts"]})

    def test_valid_standard_etf_is_eligible(self):
        self.assertEqual(evaluate_analytics_eligibility(valid_record(), POLICY, self.now), "ANALYTICS_ELIGIBLE")

    def test_missing_prior_state_is_blocked(self):
        record = valid_record(); record["prior_states"] = ["DISCOVERED"]
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "BLOCKED")

    def test_missing_or_stale_core_domain_is_blocked(self):
        record = valid_record(); record["domain_coverage"]["liquidity"]["present"] = False
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "BLOCKED")
        record = valid_record(); record["domain_coverage"]["expense_ratios"]["freshness_status"] = "STALE"
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "BLOCKED")

    def test_conflict_or_unknown_quality_is_quarantined(self):
        record = valid_record(); record["critical_conflict"] = True
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "QUARANTINED")
        record = valid_record(); record["quality_status"] = "UNKNOWN"
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "QUARANTINED")

    def test_new_fund_can_only_be_provisional(self):
        record = valid_record(); record["price_history_trading_days"] = 100
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "ANALYTICS_PROVISIONAL")
        self.assertFalse(POLICY["provisional_status_grants_certified_analytics"])

    def test_specialized_product_requires_specific_coverage(self):
        record = valid_record(); record["specialized_product_type"] = "LEVERAGED"; record["strategy_specific_coverage_complete"] = False
        self.assertEqual(evaluate_analytics_eligibility(record, POLICY, self.now), "BLOCKED")

    def test_duplicate_snapshot_identity_is_blocked(self):
        record = valid_record()
        with self.assertRaises(AnalyticsEligibilityError):
            validate_snapshot([record, copy.deepcopy(record)])

    def test_eligibility_grants_no_downstream_authority(self):
        self.assertFalse(POLICY["analytics_eligibility_grants_recommendation_authority"])
        self.assertFalse(POLICY["analytics_eligibility_grants_portfolio_suitability"])
        self.assertFalse(POLICY["analytics_eligibility_grants_execution_authority"])


if __name__ == "__main__":
    unittest.main()
