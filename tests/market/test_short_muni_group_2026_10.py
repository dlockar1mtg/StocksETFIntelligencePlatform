"""Short-duration municipal peer group (owner decision 2026-10-10, grouping version 2026-10-10.1).

Synthetic data only. Short muni funds used to have no reference near their duration: in the 2025
classification SHM, SUB and JMST correlated most with HYG and sat in high yield. SHM is now the
reference for BOND_SHORT_MUNICIPAL; every other rule is unchanged.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from foundation.market import provisional_package as P
from foundation.market import provisional_peer_groups as G
from foundation.market import provisional_ranking as R

ROOT = Path(__file__).resolve().parents[2]
RANKING_POLICY = json.loads((ROOT / "config" / "market" / "provisional_ranking_policy.json").read_text(encoding="utf-8"))
MARKET_POLICY = json.loads((ROOT / "config" / "market" / "hosted_market_data_policy.json").read_text(encoding="utf-8"))


class MuniUniverse:
    """Independent reference series, with HYG, MUB and SHM built so that short munis correlate more with HYG
    than with MUB, as SHM, SUB and JMST did in the 2025 classification, plus a short-muni factor of their own."""

    def __init__(self, n=48, seed=5):
        self.rng = np.random.default_rng(seed)
        self.ms = [f"{2021 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]
        vol = {r: 0.045 for r in G.REFERENCE_GROUP}
        vol.update({"BIL": 0.0005, "SHY": 0.004, "IEF": 0.015, "TLT": 0.035, "TIP": 0.012, "LQD": 0.02})
        self.base = {r: 0.005 + vol[r] * self.rng.normal(0, 1, n) for r in G.REFERENCE_GROUP}
        credit, rates, short = (self.rng.normal(0, 1, n) for _ in range(3))
        self.base["HYG"] = 0.004 + 0.02 * credit
        self.base["MUB"] = 0.003 + 0.012 * (0.3 * credit + 0.95 * rates)
        self.base["SHM"] = 0.002 + 0.004 * (0.9 * credit + 0.15 * rates + 0.41 * short)
        self.returns = {r: dict(zip(self.ms, v)) for r, v in self.base.items()}

    def add(self, symbol, series):
        self.returns[symbol] = dict(zip(self.ms, np.asarray(series, dtype=float)))

    def noise(self, sd):
        return self.rng.normal(0, sd, len(self.ms))

    def groups(self, symbols, without=()):
        returns = {s: r for s, r in self.returns.items() if s not in without}
        return G.classify_all(returns, list(symbols), self.ms[-1])


class ShortMuniGroupTests(unittest.TestCase):
    def setUp(self):
        u = self.u = MuniUniverse()
        sd = 0.0006
        u.add("SUBX", u.base["SHM"] + u.noise(sd))                              # short national munis
        u.add("ULTRA", 0.6 * u.base["SHM"] + 0.001 + u.noise(sd / 2))          # ultra-short munis (JMST-like)
        u.add("TERM", 1.2 * u.base["SHM"] + u.noise(sd))                        # a 2-3 year term muni ladder
        u.add("NATL", u.base["MUB"] + u.noise(0.002))                           # intermediate national munis
        u.add("JUNK", u.base["HYG"] + u.noise(0.003))                           # high-yield corporates
        u.add("TSY", u.base["SHY"] + u.noise(0.0005))                           # short Treasuries
        u.add("CORP", u.base["LQD"] + u.noise(0.003))                           # investment-grade corporates
        self.short = ("SUBX", "ULTRA", "TERM")
        self.others = {"NATL": "BOND_MUNICIPAL", "JUNK": "BOND_HIGH_YIELD", "TSY": "BOND_SHORT_TREASURY",
                       "CORP": "BOND_INVESTMENT_GRADE_CORPORATE"}

    def test_shm_is_the_short_municipal_reference(self):
        self.assertEqual(G.REFERENCE_GROUP["SHM"], "BOND_SHORT_MUNICIPAL")
        self.assertEqual(G.CLASS_OF["SHM"], "BONDS")
        self.assertEqual(self.u.groups(["SHM"])["SHM"]["group"], "BOND_SHORT_MUNICIPAL")

    def test_short_muni_funds_land_in_the_short_municipal_group(self):
        g = self.u.groups(self.short)
        for s in self.short:
            self.assertEqual(g[s]["group"], "BOND_SHORT_MUNICIPAL", (s, g[s]))
            self.assertEqual(g[s]["nearest_reference"], "SHM")
            self.assertEqual(g[s]["flags"], [], (s, g[s]))                    # 1.2x SHM is not leverage

    def test_without_the_reference_they_fell_into_high_yield(self):
        g = self.u.groups(self.short, without=("SHM",))                           # the rules before 2026-10-10
        for s in ("SUBX", "TERM"):
            self.assertEqual(g[s]["group"], "BOND_HIGH_YIELD", (s, g[s]))

    def test_no_unrelated_fund_moves_into_the_group(self):
        before = self.u.groups(self.others, without=("SHM",))
        after = self.u.groups(self.others)
        for s, group in self.others.items():
            self.assertEqual(before[s]["group"], group, (s, before[s]))
            self.assertEqual(after[s]["group"], group, (s, after[s]))

    def test_group_is_a_ranked_bond_group(self):
        self.assertEqual(R.family_of("BOND_SHORT_MUNICIPAL"), "BONDS")
        self.assertNotIn("BOND_SHORT_MUNICIPAL", RANKING_POLICY["taxonomy"]["no_call_groups"])
        self.assertTrue(P.timing_applies("BOND_SHORT_MUNICIPAL"))

    def test_assignments_from_the_old_rules_are_not_carried_over(self):
        old = {"grouping_version": "2026-10-09.1", "funds": [
            {"symbol": "SHM", "peer_group": "BOND_HIGH_YIELD", "group_evidence": {"classified_at": "2026-03"}, "ranking_call": "BUY"}]}
        state = P.previous_state(old)["SHM"]
        self.assertIsNone(state["group"])                                        # regrouped under the new rules
        self.assertEqual(state["ranking_call"], "BUY")                           # the call still feeds the hysteresis

    def test_amendment_is_recorded_after_results(self):
        self.assertEqual(G.GROUPING_VERSION, "2026-10-10.1")
        self.assertEqual(RANKING_POLICY["taxonomy"]["grouping_version"], G.GROUPING_VERSION)
        self.assertEqual(RANKING_POLICY["policy_version"], "1.2.0")
        last = RANKING_POLICY["amendments"][-1]
        self.assertEqual(last["on"], "2026-10-10")
        self.assertTrue(last["after_results"])
        self.assertEqual(last["authorized_by"], "Devon Lockard")
        self.assertIn("BOND_SHORT_MUNICIPAL", last["change"])
        self.assertIn("2026-10-10.1", last["change"])
        self.assertFalse(any("SHM" in t for t in RANKING_POLICY["known_limitations"]))
        self.assertIn("SHM", MARKET_POLICY["universe"]["style_reference_funds"])
        self.assertEqual(MARKET_POLICY["amendments"][-1]["date"], "2026-10-10")

    def test_reference_is_in_the_model_universe(self):
        doc = json.loads((ROOT / MARKET_POLICY["universe"]["model_universe_path"]).read_text(encoding="utf-8-sig"))
        self.assertIn("SHM", {r["symbol"].upper() for r in doc["records"]})


if __name__ == "__main__":
    unittest.main()
