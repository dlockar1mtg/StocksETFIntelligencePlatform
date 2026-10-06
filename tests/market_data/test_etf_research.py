"""ETF analytics and the walk-forward research harness, on synthetic series with known answers."""
from __future__ import annotations

import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path

from foundation.market_data import analytics as A
from foundation.market_data import research as R

ROOT = Path(__file__).resolve().parents[2]
MODEL = json.loads((ROOT / "config" / "market" / "etf_v1_model.json").read_text(encoding="utf-8"))


def weekdays(start: str, n: int) -> list[str]:
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def make(ticker: str, daily: list[float], start="2000-01-03", dividend_every=0, dividend=0.0) -> A.Series:
    days = weekdays(start, len(daily) + 1)
    close, tr, div = [100.0], [100.0], [0.0]
    for k, r in enumerate(daily, start=1):
        d = dividend if dividend_every and k % dividend_every == 0 else 0.0
        c = close[-1] * (1 + r) - d
        close.append(c)
        tr.append(tr[-1] * (c + d) / close[-2])
        div.append(d)
    return A.Series(ticker, days, close, tr, div)


class AnalyticsTests(unittest.TestCase):
    def test_returns_volatility_and_drawdown(self):
        s = make("X", [0.0004] * 1000)
        self.assertAlmostEqual(A.annualized(s, 252), 1.0004 ** 252 - 1, places=6)
        self.assertAlmostEqual(A.volatility(s, 252), 0.0, places=9)
        self.assertEqual(A.max_drawdown(s), 0.0)
        crash = make("Y", [0.001] * 300 + [-0.01] * 50 + [0.001] * 100)
        self.assertAlmostEqual(A.max_drawdown(crash), 0.99 ** 50 - 1, places=6)
        self.assertLess(A.drawdown_now(crash), 0)
        self.assertGreater(A.trend_ratio(make("Z", [0.001] * 300)), 1)

    def test_yield_counts_trailing_distributions(self):
        s = make("D", [0.0] * 600, dividend_every=63, dividend=0.5)
        self.assertAlmostEqual(A.trailing_yield(s), 4 * 0.5 / s.close[-1], places=6)
        self.assertLess(s.close[-1], s.close[0])        # the price drops by each distribution...
        self.assertAlmostEqual(s.tr[-1], s.tr[0])      # ...which total return adds back

    def test_correlation_and_tracking_difference(self):
        rs = [0.01 * math.sin(k) for k in range(800)]
        a, b = make("A", rs), make("B", [r - 0.0002 / 252 * 252 / 252 for r in rs])
        ra, rb = A.aligned_returns(a, b, 756)
        self.assertGreater(A.correlation(ra, rb), 0.999)
        self.assertGreater(A.tracking_difference(a, b), 0)
        self.assertAlmostEqual(A.spearman(list(range(30)), [v * v for v in range(30)]), 1.0)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.cash = make("BIL", [0.0001] * 4000, start="2005-01-03")

    def test_plain_buying_baseline(self):
        flat = make("F", [0.0] * 4000, start="2005-01-03")
        base = R.simulate(flat, self.cash, "2006-01", 36, None, None, 100, 12)
        self.assertAlmostEqual(base["value"], 3600, places=6)
        paused = R.simulate(flat, self.cash, "2006-01", 36, "WAIT_FOR_DIP", 0.10, 100, 12)
        self.assertGreater(paused["paused_months"], 0)
        self.assertGreater(paused["value"], base["value"])    # flat fund: cash interest wins

    def test_walk_forward_rejects_rules_on_a_steady_riser(self):
        riser = make("R", [0.0005] * 4000, start="2005-01-03")
        report = R.walk_forward({"R": riser}, self.cash, MODEL)
        for family, result in report.items():
            self.assertFalse(result["passes_gate"], family)
            if result["out_of_sample_starts"]:
                self.assertLessEqual(result["median_edge"], 0.0, family)

    def test_signal_study_and_cross_section_shapes(self):
        a = make("A", [0.0004 + 0.01 * math.sin(k / 40) for k in range(3000)])
        b = make("B", [0.0003 + 0.01 * math.cos(k / 50) for k in range(3000)])
        c = make("C", [0.0002] * 3000)
        study = R.signal_study({"A": a, "B": b})
        self.assertIn("stretch_36m", study["pooled"])
        xs = R.cross_sectional_momentum({"A": a, "B": b, "C": c}, ["A", "B", "C"], 12)
        self.assertGreater(xs["months"], 50)

    def test_gate_is_registered_before_results(self):
        self.assertTrue(MODEL["registered_before_results"])
        self.assertEqual(MODEL["primary_horizon_months"], 36)
        self.assertFalse(MODEL["automatic_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
