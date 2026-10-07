"""Phase 4.2: provisional peer groups, walk-forward ranking harness, timing study and the gate."""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import numpy as np

from foundation.market import provisional_peer_groups as G
from foundation.market import provisional_ranking as R

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config" / "market" / "provisional_ranking_policy.json").read_text(encoding="utf-8"))


def months(n, start=2015):
    return [f"{start + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]


class PeerGroupTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        ms = months(48)
        base = {r: rng.normal(0.006, 0.04, 48) for r in G.REFERENCE_GROUP}
        self.returns = {r: dict(zip(ms, v)) for r, v in base.items()}
        self.ms = ms
        self.base = base

    def add(self, symbol, series):
        self.returns[symbol] = dict(zip(self.ms, series))

    def test_tracker_joins_its_reference_group(self):
        self.add("TRK", self.base["EFA"] + np.random.default_rng(1).normal(0, 0.002, 48))
        self.assertEqual(G.classify("TRK", self.returns, self.ms[-1])["group"], "INTL_DEVELOPED_EQUITY")

    def test_leverage_and_inverse_come_from_behaviour_not_names(self):
        self.add("LEV", 3 * self.base["SPY"])
        self.add("INV", -1 * self.base["SPY"])
        self.assertEqual(G.classify("LEV", self.returns, self.ms[-1])["group"], "SPECIALIZED_LEVERAGED")
        self.assertEqual(G.classify("INV", self.returns, self.ms[-1])["group"], "SPECIALIZED_INVERSE")

    def test_no_fit_is_idiosyncratic_and_short_history_insufficient(self):
        self.add("ODD", np.random.default_rng(3).normal(0, 0.05, 48))
        self.assertEqual(G.classify("ODD", self.returns, self.ms[-1])["group"], "IDIOSYNCRATIC")
        self.assertEqual(G.classify("ODD", self.returns, self.ms[10])["group"], "INSUFFICIENT_HISTORY")

    def test_classification_is_point_in_time(self):
        self.add("TRK", self.base["EEM"])
        early = G.classify("TRK", self.returns, self.ms[30])
        self.returns["TRK"].update({m: 0.0 for m in self.ms[31:]})
        self.assertEqual(G.classify("TRK", self.returns, self.ms[30]), early)


class RankingHarnessTests(unittest.TestCase):
    def test_spearman_and_bands_with_hysteresis(self):
        self.assertAlmostEqual(R.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0)
        self.assertTrue(math.isnan(R.spearman([1, 2], [1, 2])))
        bands = POLICY["calls"]["bands_percentile"]
        self.assertEqual(R.assign_call(85, None, bands), "BUY")
        self.assertEqual(R.assign_call(72, "BUY", bands), "BUY")
        self.assertEqual(R.assign_call(72, None, bands), "ACCUMULATE")
        self.assertEqual(R.assign_call(25, "AVOID", bands), "AVOID")
        self.assertEqual(R.assign_call(10, None, bands), "AVOID")

    def test_factor_selection_uses_only_realized_targets(self):
        ic = {k: {} for k in R.FACTORS}
        for y in range(2005, 2020):
            for m in range(1, 13):
                ic["mom_6"][f"{y}-{m:02d}"] = 0.08 + 0.01 * (m % 3)
        chosen = R.select_factors(ic, "2012-01", 12, POLICY)
        self.assertEqual(chosen, {"mom_6": 1})
        self.assertEqual(R.select_factors(ic, "2008-01", 12, POLICY), {})   # fewer than 5 realized years

    def test_composite_skips_missing_factors(self):
        members = [{"mom_6": 0.1, "vol_1y": math.nan}, {"mom_6": 0.3, "vol_1y": 0.2}, {"mom_6": 0.2, "vol_1y": 0.1}]
        scores = R.composite(members, {"mom_6": 1, "vol_1y": -1})
        self.assertEqual(len(scores), 3)
        self.assertTrue(all(s == s for s in scores))
        self.assertGreater(scores[1], scores[0])

    def test_gate_is_preregistered_and_liquidity_is_excluded(self):
        self.assertTrue(POLICY["registered_before_results"])
        self.assertNotIn("log_adv_63", R.FACTORS)
        self.assertNotIn("log_adv_63", POLICY["factors"]["candidates"])
        self.assertTrue(POLICY["amendments"][0]["after_results"])
        empty = {"12m": {"results": {}}, "36m": {"results": {}}}
        self.assertFalse(R.gate(empty, POLICY)["pass_12m"])
        self.assertFalse(POLICY["authority"]["automatic_execution"])


if __name__ == "__main__":
    unittest.main()
