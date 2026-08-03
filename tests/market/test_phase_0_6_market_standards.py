from __future__ import annotations

import copy
import unittest
from pathlib import Path

from foundation.validation.contracts import load_json
from foundation.validation.market_standards import (
    MarketStandardValidationError,
    validate_corporate_action_policy,
    validate_market_calendar,
    validate_point_in_time_action,
    validate_return_standard,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase06MarketStandardsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calendar = load_json(ROOT / "config/market/market_calendar.json")
        self.returns = load_json(ROOT / "config/market/return_standard.json")
        self.actions = load_json(ROOT / "config/market/corporate_action_policy.json")

    def test_market_calendar_is_fail_closed(self) -> None:
        validate_market_calendar(self.calendar)
        self.assertTrue(self.calendar["unknown_calendar_dates_blocked"])
        self.assertTrue(self.calendar["early_close_requires_explicit_record"])

    def test_market_calendar_uses_required_timezone_and_tier(self) -> None:
        self.assertEqual(self.calendar["timezone"], "America/New_York")
        self.assertEqual(self.calendar["holiday_source_tier_required"], 1)

    def test_non_trading_days_cannot_generate_returns(self) -> None:
        weakened = copy.deepcopy(self.calendar)
        weakened["non_trading_days_generate_returns"] = True
        with self.assertRaises(MarketStandardValidationError):
            validate_market_calendar(weakened)

    def test_total_return_basis_is_required(self) -> None:
        validate_return_standard(self.returns)
        self.assertEqual(self.returns["security_return_basis"], "total_return")
        self.assertEqual(self.returns["benchmark_return_basis"], "total_return")

    def test_mixed_or_price_return_comparisons_are_blocked(self) -> None:
        weakened = copy.deepcopy(self.returns)
        weakened["benchmark_return_basis"] = "price_return"
        with self.assertRaises(MarketStandardValidationError):
            validate_return_standard(weakened)

    def test_corporate_action_policy_is_complete(self) -> None:
        validate_corporate_action_policy(self.actions)
        self.assertIn("LIQUIDATION", self.actions["supported_actions"])
        self.assertFalse(self.actions["retroactive_silent_rewrite"])

    def test_unknown_or_conflicting_actions_fail_closed(self) -> None:
        weakened = copy.deepcopy(self.actions)
        weakened["conflicting_actions_quarantined"] = False
        with self.assertRaises(MarketStandardValidationError):
            validate_corporate_action_policy(weakened)

    def test_point_in_time_action_rejects_look_ahead(self) -> None:
        action = {
            "announcement_date": "2026-08-10",
            "effective_date": "2026-08-20",
        }
        with self.assertRaises(MarketStandardValidationError):
            validate_point_in_time_action(action, "2026-08-03")
        validate_point_in_time_action(action, "2026-08-15")


if __name__ == "__main__":
    unittest.main()
