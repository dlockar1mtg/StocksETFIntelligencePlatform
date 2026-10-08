"""Phase 4.6: own-history outlooks, the category test, loose-peer readings (synthetic data only)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from foundation.market import provisional_full_coverage as F
from tests.market.test_provisional_projection import fund, months

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config" / "market" / "provisional_full_coverage_policy.json").read_text(encoding="utf-8"))


class OutlookTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(5)
        self.ms = months(240)
        self.spy = rng.normal(0.008, 0.045, 240)
        self.f = fund(rng.normal(0.004, 0.06, 240), self.ms)

    def test_outlook_is_ordered_deterministic_and_uses_no_later_month(self):
        a = F.own_history_outlook(self.f, self.ms[150], "ABC")
        self.assertLess(a["p10"], a["p50"])
        self.assertLess(a["p50"], a["p90"])
        self.assertEqual(a, F.own_history_outlook(self.f, self.ms[150], "ABC"))
        b = F.own_history_outlook({**self.f, "months": self.ms[:151], "tr": self.f["tr"][:151],
                                   "index": {m: i for i, m in enumerate(self.ms[:151])}}, self.ms[150], "ABC")
        self.assertEqual(a, b)                                                             # history cut at month 150: same
        self.assertEqual(a["basis"], "OWN_HISTORY")

    def test_needs_36_months(self):
        self.assertIsNone(F.own_history_outlook(self.f, self.ms[30], "ABC"))
        self.assertIsNotNone(F.own_history_outlook(self.f, self.ms[37], "ABC"))

    def test_a_decaying_inverse_fund_carries_its_decay(self):
        inv = fund(-3 * self.spy - 0.004, self.ms)
        o = F.own_history_outlook(inv, self.ms[-1], "INV")
        self.assertLess(o["p50"], 0)
        self.assertGreater(o["chance_of_loss"], 0.5)

    def test_categories(self):
        self.assertEqual(F.category({"group": "IDIOSYNCRATIC"}, None), "IDIOSYNCRATIC")
        self.assertEqual(F.category({"group": "US_EQUITY_LARGE_BLEND"}, "MOVES_FAR_MORE_THAN_ITS_REFERENCE"), "MOVES_FAR_MORE_THAN_ITS_REFERENCE")
        self.assertIsNone(F.category({"group": "US_EQUITY_LARGE_BLEND"}, None))
        self.assertIsNone(F.category({"group": "INSUFFICIENT_HISTORY"}, None))


class CoverageTests(unittest.TestCase):
    def test_every_left_out_fund_gets_an_outlook_and_a_reading_never_a_call(self):
        rng = np.random.default_rng(9)
        ms = months(120)
        spy = rng.normal(0.008, 0.045, 120)
        features = {s: fund(spy * k + rng.normal(0, 0.01, 120), ms) for s, k in
                    (("IDI", 0.5), ("L1", 3), ("L2", 3), ("L3", 2), ("L4", 2), ("L5", 3), ("P1", 1), ("P2", 1), ("P3", 1), ("P4", 1), ("P5", 1))}

        def rec(sym, group, fee, ref="SPY", call="NO_CALL_SPECIALIZED_OR_UNGROUPED"):
            return {"symbol": sym, "usage": "MODEL", "peer_group": group, "expense_ratio": fee, "ranking_call": call,
                    "group_evidence": {"nearest_reference": ref, "correlation": 0.55}, "projection_3y": None}
        records = [rec("IDI", "IDIOSYNCRATIC", 0.004)] + [rec(f"L{i}", "SPECIALIZED_LEVERAGED", 0.009 + i / 1e4) for i in range(1, 6)] \
            + [rec(f"P{i}", "US_EQUITY_LARGE_BLEND", 0.0003 * i, call="HOLD") for i in range(1, 6)]
        groups = {"US_EQUITY_LARGE_BLEND": {"when_to_buy": {"rule": None, "verdict": "STEADY_BUYING"}}}
        research = {"category_status": {"IDIOSYNCRATIC": "TESTED"}, "categories": {"IDIOSYNCRATIC": {"inside_10_90": 0.66}}}
        before = [r["ranking_call"] for r in records]
        out = F.add_full_coverage(records, groups, features, ms[-1], research)
        by = {r["symbol"]: r for r in records}
        self.assertEqual(out["outlook_total"], 6)
        self.assertEqual(by["IDI"]["outlook_3y"]["status"], "TESTED")
        self.assertEqual(by["L1"]["outlook_3y"]["status"], "UNTESTED")
        self.assertEqual(by["IDI"]["loose_peer_reading"]["peer_group"], "US_EQUITY_LARGE_BLEND")
        self.assertEqual(by["IDI"]["loose_peer_reading"]["cost_percentile"], 0.0)            # dearer than every peer
        self.assertTrue(by["IDI"]["when_to_buy"]["loose"])
        self.assertEqual(by["L1"]["loose_peer_reading"]["basis"], "SAME_KIND_PEERS")
        self.assertEqual(by["L1"]["loose_peer_reading"]["cost_percentile"], 100.0)           # cheapest leveraged fund
        self.assertNotIn("when_to_buy", by["L1"])
        self.assertNotIn("outlook_3y", by["P1"])
        self.assertEqual([r["ranking_call"] for r in records], before)                     # readings are never calls
        self.assertTrue(all(r["loose_peer_reading"]["call"] is None for r in records if r.get("loose_peer_reading")))

    def test_category_test_runs_walk_forward(self):
        rng = np.random.default_rng(1)
        ms = months(300, start=1999)
        spy = rng.normal(0.007, 0.045, 300)
        features = {"SPY": fund(spy, ms), "BIL": fund(np.full(300, 0.002), ms, 0.03), "SHY": fund(np.full(300, 0.0025), ms, 0.035)}
        for i in range(8):
            features[f"I{i}"] = fund(rng.normal(0.005, 0.05, 300), ms)
        groups = {y: {s: {"group": "IDIOSYNCRATIC", "nearest_reference": "SPY"} for s in features if s.startswith("I")} for y in range(2004, 2024)}
        res = F.calibration_test(features, [s for s in features if s.startswith("I")], groups, POLICY)
        self.assertGreater(res["categories"]["IDIOSYNCRATIC"]["n"], 50)
        self.assertEqual(res["test_starts"][0], 2005)
        self.assertLessEqual(max(res["test_starts"]), 2020)                                # 36 months must have ended
        self.assertIn(res["category_status"]["IDIOSYNCRATIC"], ("TESTED", "TOO_FEW_TESTS", "TOO_CAUTIOUS", "TOO_NARROW"))


if __name__ == "__main__":
    unittest.main()
