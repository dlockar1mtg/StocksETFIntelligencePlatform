from __future__ import annotations

import copy
import json
import unittest
from datetime import date
from pathlib import Path

from foundation.market.historical_data_authority import (
    HistoricalDataAuthorityError,
    load_policy,
    validate_candidate_universe,
    validate_contract_registration,
    validate_observation,
)

ROOT = Path(__file__).resolve().parents[2]


def candidate_document() -> dict:
    records = [
        {"security_id": f"SEC-{index}", "symbol": f"ETF{index}", "screen_state": "MARKET_DATA_ELIGIBLE"}
        for index in range(3459)
    ]
    records.extend([
        {"security_id": "SEC-VOO", "symbol": "VOO", "screen_state": "MARKET_DATA_ELIGIBLE"},
        {"security_id": "SEC-SCHD", "symbol": "SCHD", "screen_state": "MARKET_DATA_ELIGIBLE"},
        {"security_id": "SEC-QQQM", "symbol": "QQQM", "screen_state": "MARKET_DATA_ELIGIBLE"},
    ])
    return {
        "record_count": 3462,
        "admission_state": "MARKET_DATA_ELIGIBLE",
        "provisional_records_included": False,
        "records": records,
    }


def observation() -> dict:
    return {
        "security_id": "SEC-VOO",
        "symbol": "VOO",
        "provider_id": "YAHOO_FINANCE_CHART",
        "provider_symbol": "VOO",
        "observation_date": "2026-08-03",
        "available_at_utc": "2026-08-04T01:00:00Z",
        "raw_close": 600.0,
        "adjusted_close": 599.0,
        "volume": 1000000,
        "dividend_amount": 0.0,
        "split_ratio": 1.0,
        "return_basis": "TOTAL_RETURN",
        "corporate_action_state": "CLEAR",
        "source_lineage": {
            "source_url": "https://example.test/VOO",
            "raw_path": "data/raw/VOO.json",
            "content_sha256": "a" * 64,
            "retrieved_at_utc": "2026-08-04T01:00:00Z",
        },
        "authority": {
            "normalization": True,
            "return_calculation": False,
            "risk_analytics": False,
            "forecasting": False,
            "recommendations": False,
            "automatic_execution": False,
        },
    }


class Phase31HistoricalDataAuthorityTests(unittest.TestCase):
    def test_policy_locks_certified_candidate_count(self):
        self.assertEqual(load_policy()["required_candidate_count"], 3462)

    def test_provisional_candidates_are_blocked(self):
        self.assertFalse(load_policy()["provisional_candidates_allowed"])

    def test_policy_grants_no_computed_or_decision_authority(self):
        authority = load_policy()["authority"]
        for key in ("return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"):
            self.assertFalse(authority[key])

    def test_total_return_basis_is_required(self):
        self.assertEqual(load_policy()["return_basis"]["primary_basis"], "TOTAL_RETURN")

    def test_contract_is_registered(self):
        validate_contract_registration()

    def test_valid_candidate_universe_passes(self):
        self.assertEqual(len(validate_candidate_universe(candidate_document())), 3462)

    def test_candidate_count_drift_fails_closed(self):
        document = candidate_document()
        document["records"].pop()
        with self.assertRaises(HistoricalDataAuthorityError):
            validate_candidate_universe(document)

    def test_provisional_record_cannot_enter_phase_3(self):
        document = candidate_document()
        document["records"][0]["screen_state"] = "MARKET_DATA_PROVISIONAL"
        with self.assertRaises(HistoricalDataAuthorityError):
            validate_candidate_universe(document)

    def test_valid_observation_passes(self):
        self.assertEqual(validate_observation(observation(), date(2026, 8, 4))["symbol"], "VOO")

    def test_future_observation_fails_closed(self):
        record = observation()
        record["observation_date"] = "2026-08-05"
        with self.assertRaises(HistoricalDataAuthorityError):
            validate_observation(record, date(2026, 8, 4))

    def test_symbol_mismatch_fails_closed(self):
        record = observation()
        record["provider_symbol"] = "VOOG"
        with self.assertRaises(HistoricalDataAuthorityError):
            validate_observation(record, date(2026, 8, 4))

    def test_corporate_action_conflict_fails_closed(self):
        record = observation()
        record["corporate_action_state"] = "CONFLICTED"
        with self.assertRaises(HistoricalDataAuthorityError):
            validate_observation(record, date(2026, 8, 4))


if __name__ == "__main__":
    unittest.main()
