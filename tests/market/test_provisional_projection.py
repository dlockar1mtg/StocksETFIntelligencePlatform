"""Phase 4.5: 3-year projections, center selection and the calibration test (synthetic data only)."""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import numpy as np

from foundation.market import provisional_projection as P

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config" / "market" / "provisional_projection_policy.json").read_text(encoding="utf-8"))


def months(n, start=2000):
    return [f"{start + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]


def fund(rets, ms, yield_=0.0):
    tr = np.cumprod(np.concatenate([[100.0], 1 + np.array(rets)]))[1:]
    close = tr.copy()
    return {"security_id": "x", "months": ms, "index": {m: i for i, m in enumerate(ms)}, "date": [f"{m}-28" for m in ms],
            "tr": tr, "close": close, "div_12m": close * yield_, "trend_200": tr * 0, "vol_1y": tr * 0, "dd_now": tr * 0,
            "maxdd_3y": tr * 0, "adv_63": tr * 0 + 1e7}


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.ms = months(240)
        spy = rng.normal(0.008, 0.045, 240)
        self.features = {"SPY": fund(spy, self.ms), "BIL": fund(np.full(240, 0.002), self.ms, 0.03),
                         "SHY": fund(np.full(240, 0.0025), self.ms, 0.035),
                         "TRK": fund(spy + rng.normal(0, 0.002, 240), self.ms),
                         "LEV": fund(3 * spy, self.ms)}
        self.group = {"group": "US_EQUITY_LARGE_BLEND", "nearest_reference": "SPY"}

    def test_a_tracker_gets_an_ordered_range_from_its_reference(self):
        p = P.Projector(self.features).project("TRK", self.group, self.ms[-1])
        self.assertEqual(p["reference"], "SPY")
        self.assertAlmostEqual(p["beta"], 1.0, delta=0.05)
        self.assertLess(p["p10"], p["p50"])
        self.assertLess(p["p50"], p["p90"])
        self.assertTrue(0 <= p["chance_of_loss"] <= 1)
        self.assertEqual(p["center_rule"], "CASH_PLUS_BETA")
        self.assertGreater(p["growth_of_1000"]["p90"], p["growth_of_1000"]["p10"])

    def test_no_projection_for_leveraged_inverse_ungrouped_or_short_history(self):
        pj = P.Projector(self.features)
        for g in ("SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "IDIOSYNCRATIC", "INSUFFICIENT_HISTORY"):
            self.assertIsNone(pj.project("LEV", {"group": g, "nearest_reference": "SPY"}, self.ms[-1]))
        self.assertIsNone(pj.project("TRK", self.group, self.ms[40]))           # reference under 60 months

    def test_a_higher_fee_lowers_the_center_by_the_fee_gap(self):
        cheap = P.Projector(self.features, lambda s, d: 0.0003).project("TRK", self.group, self.ms[-1])
        dear = P.Projector(self.features, lambda s, d: 0.0103 if s == "TRK" else 0.0003).project("TRK", self.group, self.ms[-1])
        self.assertAlmostEqual(dear["fee_gap"], 0.01)
        gap = math.log1p(cheap["centers"]["CASH_PLUS_BETA"]) - math.log1p(dear["centers"]["CASH_PLUS_BETA"])
        self.assertAlmostEqual(gap, 0.01, places=3)             # centers are rounded to 4 places

    def test_projection_is_point_in_time(self):
        end = self.ms[150]
        before = P.Projector(self.features).project("TRK", self.group, end)
        self.features["TRK"]["tr"][151:] *= 3                                  # the future changes
        self.features["SPY"]["tr"][151:] *= 0.2
        self.assertEqual(P.Projector(self.features).project("TRK", self.group, end), before)

    def test_center_rules_are_chosen_from_finished_starts_only(self):
        errors = {"US_EQUITY": {2005: {"OWN_HISTORY": [0.01] * 30, "CASH_PLUS_BETA": [0.05] * 30},
                                2006: {"OWN_HISTORY": [0.01] * 30, "CASH_PLUS_BETA": [0.05] * 30},
                                2007: {"OWN_HISTORY": [0.01] * 30, "CASH_PLUS_BETA": [0.05] * 30}}}
        self.assertEqual(P.choose_rules(errors, 2009)["US_EQUITY"], "CASH_PLUS_BETA")   # 2007 not finished by 2009
        self.assertEqual(P.choose_rules(errors, 2010)["US_EQUITY"], "OWN_HISTORY")

    def test_family_status_follows_the_amendment(self):
        fams = {"A": {"n": 500, "inside_10_90": 0.82}, "B": {"n": 500, "inside_10_90": 0.96},
                "C": {"n": 500, "inside_10_90": 0.55}, "D": {"n": 50, "inside_10_90": 0.8}}
        self.assertEqual(P.family_status(fams, POLICY), {"A": "TESTED", "B": "TOO_CAUTIOUS", "C": "TOO_NARROW", "D": "TOO_FEW_TESTS"})

    def test_calibration_test_runs_walk_forward(self):
        groups = {y: {"TRK": self.group} for y in range(2004, 2020)}
        out = P.calibration_test(self.features, ["TRK"], groups, POLICY)
        self.assertTrue(out["observations"] > 0)
        self.assertTrue(all(int(y) + 3 <= 2019 for y in out["test_starts"]))
        self.assertTrue(0 <= out["overall"]["inside_10_90"] <= 1)
        self.assertIn("family_status", out)

    def test_the_package_attaches_projections_with_family_status(self):
        from foundation.market import provisional_package as PK

        class Stub:
            def project(self, symbol, group, end_month, rule):
                return {"p10": -0.01, "p50": 0.1, "p90": 0.2, "chance_of_loss": 0.1, "family": "US_EQUITY", "center_rule": rule}

        status = {"funds": [{"symbol": s, "security_id": f"SEC-US-{s}", "usage": "MODEL", "quality_status": "PROVISIONAL",
                             "freshness_state": "CURRENT"} for s in ("SPY", "TRK")]}
        records, groups = PK.build_records(status=status, features=self.features, research={}, cached_bars=lambda s: [],
                                           projector=Stub(), projection={"rules_now": {"US_EQUITY": "CASH_PLUS_BETA"},
                                                                         "family_status": {"US_EQUITY": "TESTED"},
                                                                         "families": {"US_EQUITY": {"inside_10_90": 0.82}}})
        trk = next(r for r in records if r["symbol"] == "TRK")
        self.assertEqual(trk["projection_3y"]["status"], "TESTED")
        self.assertEqual(trk["projection_3y"]["family_band_coverage"], 0.82)
        self.assertEqual(trk["projection_3y"]["center_rule"], "CASH_PLUS_BETA")

    def test_policy_was_registered_first_and_the_amendment_is_labelled(self):
        self.assertTrue(POLICY["registered_before_results"])
        self.assertTrue(all(a["after_results"] for a in POLICY["amendments"]))
        self.assertFalse(POLICY["authority"]["automatic_execution"])
        self.assertFalse(POLICY["results_2026_10_07"]["passes_registered_test"])


if __name__ == "__main__":
    unittest.main()
