"""ETF v1 guidance and the governed UIP package."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market_data import model as M
from foundation.market_data import package as P
from tests.market_data.test_etf_research import make

ROOT = Path(__file__).resolve().parents[2]
FUNDS = json.loads((ROOT / "config" / "market" / "monitored_funds.json").read_text(encoding="utf-8"))
MODEL = json.loads((ROOT / "config" / "market" / "etf_v1_model.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "contracts" / "uip" / "package_manifest.schema.json").read_text(encoding="utf-8"))


def world():
    import math
    base = [0.0004 + 0.01 * math.sin(k / 9) for k in range(2600)]
    other = [0.0003 + 0.012 * math.cos(k / 7) for k in range(2600)]
    series = {
        "VOO": make("VOO", base, dividend_every=63, dividend=1.0),
        "IYY": make("IYY", [r - 0.0002 / 1 / 252 * 3 for r in base]),               # same moves, a little worse
        "QQQM": make("QQQM", other), "QQQ": make("QQQ", [r - 0.00003 / 252 for r in other]),
        "SCHD": make("SCHD", [0.0003 + 0.008 * math.sin(k / 5 + 1) for k in range(2600)]),
        "IWM": make("IWM", [0.0002 + 0.015 * math.cos(k / 11 + 2) for k in range(2600)]),
        "DIA": make("DIA", [0.0003 + 0.009 * math.sin(k / 13 + 3) for k in range(2600)]),
        "EDOW": make("EDOW", [0.0003 + 0.009 * math.sin(k / 13 + 3.05) for k in range(2600)]),
        "SPY": make("SPY", base),
    }
    status = {"funds": [{"ticker": f["ticker"], "quality_status": "PROVISIONAL", "freshness_state": "CURRENT",
                         "source_tier": 4, "provider_id": "YAHOO_CHART_V8", "limitations": [], "payload": {}}
                        for f in FUNDS["funds"]]}
    return series, status


class GuidanceTests(unittest.TestCase):
    def test_duplicates_redirect_to_the_cheaper_fund_and_others_hold_steady(self):
        series, status = world()
        records = {r["ticker"]: r for r in M.build_records(FUNDS, MODEL, series, status)}
        self.assertEqual(records["QQQ"]["call"], "REDIRECT_NEW_MONEY")
        self.assertEqual(records["QQQ"]["redirect_to"], "QQQM")
        self.assertEqual(records["IYY"]["redirect_to"], "VOO")
        for t in ("VOO", "QQQM", "SCHD", "IWM", "DIA", "EDOW"):
            self.assertEqual(records[t]["call"], "STEADY_ACCUMULATION", t)
        self.assertIn("shares you already hold can stay", records["IYY"]["call_reason"])
        self.assertEqual(len(records["VOO"]["history_daily"]), 252)

    def test_never_redirects_to_a_fund_that_tracked_worse(self):
        overlaps = [{"ticker": "B", "correlation_3y": 0.999, "same_index": True, "tracking_difference_3y": 0.002,
                     "expense_ratio": 0.0001}]
        self.assertEqual(M.guidance("A", overlaps, {**MODEL["structure"], "expense_ratios": {"A": 0.002, "B": 0.0001}})["call"], "STEADY")

    def test_blocked_fund_gets_no_call(self):
        series, status = world()
        status["funds"][0]["quality_status"] = "BLOCKED"
        records = {r["ticker"]: r for r in M.build_records(FUNDS, MODEL, series, status)}
        self.assertEqual(records["VOO"]["call"], "NO_CURRENT_MARKET_PRICE")


class PackageTests(unittest.TestCase):
    def build(self, records):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        manifest = P.write_package(Path(tmp.name), records=records, research={"model_id": "ETF_V1", "timing_rules": {}},
                                   status={"funds": []}, commit="136bd0d", generated_at_utc="2026-10-06T22:30:00+00:00",
                                   schema=SCHEMA)
        return Path(tmp.name), manifest

    def test_manifest_follows_the_uip_contract_and_verifies(self):
        series, status = world()
        directory, manifest = self.build(M.build_records(FUNDS, MODEL, series, status))
        self.assertEqual(manifest["domain"], "stocks_etf")
        self.assertEqual(manifest["certification_status"], "PROVISIONAL")
        self.assertFalse(manifest["automatic_execution_authorized"])
        self.assertEqual(P.verify_package(directory, SCHEMA)["package_id"], manifest["package_id"])
        (directory / "latest_prices.csv").write_text("tampered", encoding="utf-8")
        with self.assertRaises(P.PackageError):
            P.verify_package(directory, SCHEMA)

    def test_validator_rejects_contract_breaks(self):
        good = {"package_id": "etf-2026-10-06-x", "domain": "stocks_etf", "contract_version": "1.0.0",
                "generated_at_utc": "x", "source_snapshot_id": "s", "repository_commit": "136bd0d",
                "files": [{"path": "a", "sha256": "0" * 64, "row_count": 1}], "validation_status": "PASS",
                "certification_status": "PROVISIONAL", "automatic_execution_authorized": False}
        P.validate_manifest(SCHEMA, good)
        for change in ({"automatic_execution_authorized": True}, {"domain": "crypto"}, {"files": []},
                       {"certification_status": "GOLD"}, {"extra": 1}, {"repository_commit": "XYZ"}):
            with self.assertRaises(P.PackageError, msg=change):
                P.validate_manifest(SCHEMA, {**good, **change})

    def test_stale_or_quarantined_funds_limit_the_package(self):
        series, status = world()
        status["funds"][1]["freshness_state"] = "AGING"
        status["funds"][2]["quality_status"] = "QUARANTINED"
        _, manifest = self.build(M.build_records(FUNDS, MODEL, series, status))
        self.assertEqual(manifest["validation_status"], "PASS_WITH_LIMITATIONS")
        for f in status["funds"]:
            f["quality_status"] = "BLOCKED"
        validation, _ = P.package_validation(M.build_records(FUNDS, MODEL, series, status))
        self.assertEqual(validation, "FAIL")


if __name__ == "__main__":
    unittest.main()
