from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.infrastructure.sec_fund_tickers import (
    SECFundTickerAcquisitionError,
    load_policy,
    parse_fund_ticker_payload,
    reconcile_to_universe,
    write_immutable,
)


class Phase2A3SECFundTickerTests(unittest.TestCase):
    def sample_payload(self) -> bytes:
        return json.dumps({
            "fields": ["cik", "seriesId", "classId", "ticker", "name"],
            "data": [
                [36405, "S000002839", "C000092055", "VOO", "Vanguard 500 Index Fund"],
                [11111, "S000000001", "C000000001", "DUP", "Duplicate A"],
                [22222, "S000000002", "C000000002", "DUP", "Duplicate B"],
            ],
        }).encode("utf-8")

    def test_policy_is_fail_closed_and_evidence_sized(self) -> None:
        policy = load_policy()
        self.assertTrue(policy["raw_evidence_immutable"])
        self.assertTrue(policy["fail_closed"])
        self.assertIsNone(policy["target_universe_size"])
        self.assertEqual(policy["selection_principle"], "EVIDENCE_DETERMINES_SIZE")

    def test_sec_rate_is_below_official_limit(self) -> None:
        policy = load_policy()
        self.assertLessEqual(policy["maximum_requests_per_second"], 10)
        self.assertLessEqual(policy["maximum_requests_per_second"], policy["official_sec_limit_requests_per_second"])

    def test_downstream_authority_remains_false(self) -> None:
        policy = load_policy()
        for key, value in policy["authority"].items():
            if key.endswith("development"):
                continue
            self.assertFalse(value, key)

    def test_parse_official_fund_ticker_shape(self) -> None:
        rows = parse_fund_ticker_payload(self.sample_payload())
        self.assertEqual(rows[0]["ticker"], "VOO")
        self.assertEqual(rows[0]["cik"], "0000036405")
        self.assertEqual(rows[0]["series_id"], "S000002839")
        self.assertEqual(rows[0]["class_contract_id"], "C000092055")

    def test_malformed_payload_fails_closed(self) -> None:
        with self.assertRaises(SECFundTickerAcquisitionError):
            parse_fund_ticker_payload(json.dumps({"data": []}).encode())

    def test_reconciliation_preserves_matched_conflicted_and_unmatched(self) -> None:
        rows = parse_fund_ticker_payload(self.sample_payload())
        universe = [
            {"security_id": "SEC-US-VOO", "symbol": "VOO"},
            {"security_id": "SEC-US-DUP", "symbol": "DUP"},
            {"security_id": "SEC-US-NONE", "symbol": "NONE"},
        ]
        result = reconcile_to_universe(rows, universe)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["conflicted"], 1)
        self.assertEqual(result["unmatched"], 1)
        self.assertIsNone(result["target_universe_size"])
        states = {item["symbol"]: item["reconciliation_state"] for item in result["records"]}
        self.assertEqual(states, {"VOO": "MATCHED", "DUP": "CONFLICTED", "NONE": "UNMATCHED"})

    def test_reconciliation_grants_no_analytics_or_recommendation_authority(self) -> None:
        rows = parse_fund_ticker_payload(self.sample_payload())
        result = reconcile_to_universe(rows, [{"security_id": "SEC-US-VOO", "symbol": "VOO"}])
        record = result["records"][0]
        self.assertFalse(record["analytics_authorized"])
        self.assertFalse(record["recommendations_authorized"])

    def test_immutable_raw_collision_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "raw.json"
            write_immutable(path, b"one")
            write_immutable(path, b"one")
            with self.assertRaises(SECFundTickerAcquisitionError):
                write_immutable(path, b"two")

    def test_runner_requires_declared_sec_user_agent(self) -> None:
        policy = load_policy()
        self.assertEqual(policy["required_user_agent_environment_variable"], "SEC_USER_AGENT")


if __name__ == "__main__":
    unittest.main()
