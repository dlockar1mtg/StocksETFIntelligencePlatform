import json
import unittest
from pathlib import Path

from foundation.market.issuer_batch_expansion import (
    IssuerBatchExpansionError,
    build_issuer_batch_plan,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config/market/issuer_batch_expansion_policy.json").read_text())


def manifest_record(security_id, symbol, issuer_key=None, state="PENDING"):
    return {
        "security_id": security_id,
        "symbol": symbol,
        "issuer_key": issuer_key,
        "acquisition_state": state,
    }


def pilot_record(security_id, symbol):
    return {
        "security_id": security_id,
        "symbol": symbol,
        "classification_status": "CLASSIFIED",
        "taxonomy_classification_authorized": True,
    }


class Phase36B3CIssuerBatchTests(unittest.TestCase):
    def setUp(self):
        self.policy = dict(POLICY)
        self.policy["required_full_population"] = 5
        self.manifest = {
            "records": [
                manifest_record("SEC-US-VOO", "VOO", "VANGUARD"),
                manifest_record("SEC-US-SCHD", "SCHD", "CHARLES_SCHWAB"),
                manifest_record("SEC-US-QQQM", "QQQM", "INVESCO"),
                manifest_record("SEC-US-AAA", "AAA", "ISSUER_A"),
                manifest_record("SEC-US-BBB", "BBB", None),
            ]
        }
        self.pilot = {
            "records": [
                pilot_record("SEC-US-VOO", "VOO"),
                pilot_record("SEC-US-SCHD", "SCHD"),
                pilot_record("SEC-US-QQQM", "QQQM"),
            ]
        }

    def test_policy_locks_full_population(self):
        self.assertEqual(POLICY["required_full_population"], 3462)
        self.assertEqual(POLICY["remaining_population"], 3459)

    def test_pilot_records_are_preserved_complete(self):
        result = build_issuer_batch_plan(self.manifest, self.pilot, self.policy)
        self.assertEqual(result["batch_state_counts"]["PILOT_COMPLETE"], 3)

    def test_evidence_backed_issuer_creates_batch(self):
        result = build_issuer_batch_plan(self.manifest, self.pilot, self.policy)
        self.assertEqual(result["issuer_batch_count"], 1)
        self.assertEqual(result["batches"][0]["issuer_key"], "ISSUER_A")

    def test_missing_issuer_is_preserved(self):
        result = build_issuer_batch_plan(self.manifest, self.pilot, self.policy)
        self.assertEqual(result["issuer_evidence_required_count"], 1)
        record = next(item for item in result["records"] if item["symbol"] == "BBB")
        self.assertEqual(record["batch_state"], "ISSUER_EVIDENCE_REQUIRED")

    def test_priority_is_coverage_then_issuer(self):
        self.manifest["records"].append(manifest_record("SEC-US-CCC", "CCC", "ISSUER_A"))
        self.manifest["records"].append(manifest_record("SEC-US-DDD", "DDD", "ISSUER_B"))
        self.policy["required_full_population"] = 7
        result = build_issuer_batch_plan(self.manifest, self.pilot, self.policy)
        self.assertEqual(result["batches"][0]["issuer_key"], "ISSUER_A")
        self.assertEqual(result["batches"][0]["etf_count"], 2)

    def test_duplicate_identity_fails_closed(self):
        self.manifest["records"][-1]["security_id"] = "SEC-US-AAA"
        with self.assertRaises(IssuerBatchExpansionError):
            build_issuer_batch_plan(self.manifest, self.pilot, self.policy)

    def test_incomplete_pilot_fails_closed(self):
        self.pilot["records"] = self.pilot["records"][:2]
        with self.assertRaises(IssuerBatchExpansionError):
            build_issuer_batch_plan(self.manifest, self.pilot, self.policy)

    def test_no_taxonomy_or_production_authority(self):
        result = build_issuer_batch_plan(self.manifest, self.pilot, self.policy)
        for record in result["records"]:
            self.assertFalse(record["taxonomy_dimensions_assigned"])
            self.assertFalse(record["production_taxonomy_authority"])

    def test_source_capture_remains_false(self):
        self.assertFalse(POLICY["authority"]["authoritative_source_capture"])

    def test_downstream_authorities_remain_false(self):
        for key in (
            "production_taxonomy_classification",
            "relative_return_calculation",
            "risk_analytics",
            "forecasting",
            "ranking",
        ):
            self.assertFalse(POLICY["authority"][key])


if __name__ == "__main__":
    unittest.main()
