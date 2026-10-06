"""Phase 4.1 hosted market data: universe, incremental updates, quarantine and month-end features."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from foundation.infrastructure.yahoo_chart_daily import ChartClient
from foundation.market import daily_series as S
from foundation.market import hosted_market_data as H

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "config" / "market" / "hosted_market_data_policy.json").read_text(encoding="utf-8"))
HOLIDAYS = set(POLICY["nyse_holidays"]["dates"])
NOW = datetime(2026, 10, 6, 22, 30, tzinfo=timezone.utc)


def sessions(end: str, count: int) -> list[str]:
    out, day = [], date.fromisoformat(end)
    while len(out) < count:
        if day.weekday() < 5 and day.isoformat() not in HOLIDAYS:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return sorted(out)


def chart(symbol="VOO", n=900, end="2026-10-06", start=None, split_on=None, bad_adj=None, cut=None):
    days = sessions(end, n)
    closes = [400 * (1.0004 ** i) * (1 + 0.01 * ((i % 7) - 3) / 3) for i in range(n)]
    divs = {days[i]: 1.5 for i in range(63, n, 63)}
    adj = closes[:]
    for i in range(n - 1, 0, -1):
        if days[i] in divs:
            f = 1 - divs[days[i]] / closes[i - 1]
            for j in range(i):
                adj[j] *= f
    if bad_adj is not None:
        adj[bad_adj] *= 1.05
    keep = [i for i, d in enumerate(days) if (start is None or d >= start) and (cut is None or d <= cut)]
    stamp = lambda d: int(datetime.fromisoformat(d + "T14:30:00+00:00").timestamp())
    events = {"dividends": {str(stamp(days[i])): {"amount": divs[days[i]], "date": stamp(days[i])} for i in keep if days[i] in divs}}
    if split_on:
        events["splits"] = {str(stamp(split_on)): {"date": stamp(split_on), "numerator": 2, "denominator": 1}}
    return {"chart": {"result": [{"meta": {"symbol": symbol, "currency": "USD"}, "timestamp": [stamp(days[i]) for i in keep],
            "events": events, "indicators": {"quote": [{"close": [closes[i] for i in keep], "volume": [10000] * len(keep)}],
                                             "adjclose": [{"adjclose": [adj[i] for i in keep]}]}}]}}


class UniverseTests(unittest.TestCase):
    def test_model_universe_plus_references_and_held_funds(self):
        funds = H.load_universe(ROOT, POLICY)
        model = [f for f in funds if f["usage"] == "MODEL"]
        self.assertEqual(len(model), 1077)
        symbols = {f["symbol"]: f for f in funds}
        for s in ("VOO", "SCHD", "QQQM", "QQQ", "IWM", "IYY"):
            self.assertEqual(symbols[s]["usage"], "MODEL")
        self.assertEqual(symbols["EDOW"]["usage"], "HELD_OUTSIDE_MODEL")
        self.assertEqual(len(symbols), len(funds))
        self.assertFalse(POLICY["authority"]["ranking"])


class UpdateTests(unittest.TestCase):
    fund = {"security_id": "SEC-US-VOO", "symbol": "VOO", "usage": "MODEL"}

    def test_incremental_update_continues_the_full_series_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            first = H.update_fund(self.fund, lambda s, start: chart(cut="2026-09-15"), POLICY, NOW, cache)
            self.assertEqual(first["mode"], "FULL")
            self.assertTrue(first["accepted_this_run"], first["failures"])
            # same underlying history, fetched from an overlap start
            full = chart(n=900)
            calls = []

            def fetch(symbol, start):
                calls.append(start)
                return chart(n=900, start=(start.date().isoformat() if start else None))
            second = H.update_fund(self.fund, fetch, POLICY, NOW, cache)
            self.assertEqual(second["mode"], "INCREMENTAL", second)
            self.assertTrue(second["accepted_this_run"], second["failures"])
            self.assertIsNotNone(calls[0])
            reference = S.parse_yahoo_chart(full, "VOO", now_utc=NOW)
            S.reconstruct_total_return(reference.bars)
            cached = H.read_cached_bars(cache, "VOO")
            self.assertEqual(cached[-1].day, "2026-10-06")
            ratio = cached[-1].tr_index / cached[-200].tr_index
            ref_ratio = reference.bars[-1].tr_index / reference.bars[-200].tr_index
            self.assertAlmostEqual(ratio, ref_ratio, places=4)

    def test_new_split_forces_a_full_refetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            H.update_fund(self.fund, lambda s, start: chart(cut="2026-09-15"), POLICY, NOW, cache)
            starts = []

            def fetch(symbol, start):
                starts.append(start)
                return chart(n=900, start=start.date().isoformat() if start else None, split_on="2026-10-01")
            record = H.update_fund(self.fund, fetch, POLICY, NOW, cache)
            self.assertEqual(record["mode"], "FULL")
            self.assertIsNone(starts[-1])

    def test_failed_reconciliation_keeps_the_last_good_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            H.update_fund(self.fund, lambda s, start: chart(cut="2026-09-15"), POLICY, NOW, cache)
            kept = (cache / "VOO.csv").read_text()
            record = H.update_fund(self.fund, lambda s, start: chart(bad_adj=850), POLICY, NOW, cache, full_refresh=True)
            self.assertEqual(record["quality_status"], "QUARANTINED")
            self.assertEqual((cache / "VOO.csv").read_text(), kept)
            self.assertEqual(record["freshness_state"], "STALE")

    def test_missing_fund_is_blocked_not_fatal(self):
        def missing(symbol, start):
            raise LookupError(f"{symbol}: not found")
        with tempfile.TemporaryDirectory() as tmp:
            record = H.update_fund(self.fund, missing, POLICY, NOW, Path(tmp))
            self.assertEqual(record["quality_status"], "BLOCKED")


class FeatureTests(unittest.TestCase):
    def test_month_end_features_use_no_future_data(self):
        parsed = S.parse_yahoo_chart(chart(n=900), "VOO", now_utc=NOW)
        S.reconstruct_total_return(parsed.bars)
        fund = {"security_id": "SEC-US-VOO", "symbol": "VOO"}
        rows = H.month_end_features(fund, parsed.bars)
        self.assertGreater(len(rows), 30)
        target = rows[30]
        cut = [b for b in parsed.bars if b.day <= target["date"]] + [S.Bar("2099-01-02", 1.0, None, 1, 0.0, 1.0, 1.0)]
        again = {r["date"]: r for r in H.month_end_features(fund, cut)}[target["date"]]
        self.assertEqual(again, target)
        self.assertNotEqual(rows[-1]["date"], "2026-10-06")          # the current month is not complete yet
        self.assertEqual(set(rows[0]), set(H.FEATURE_FIELDS))


class ClientTests(unittest.TestCase):
    def test_paces_requests_and_builds_period_urls(self):
        slept, t = [], [0.0]
        client = ChartClient(POLICY["provider"], sleep=lambda s: slept.append(s), clock=lambda: t[0])
        client._pace()
        client._pace()
        self.assertTrue(slept and slept[-1] > 0)
        url = client.url("VOO", 100, 200)
        self.assertIn("period1=100", url)
        self.assertIn("events=div%2Csplits", url)
        with self.assertRaises(ValueError):
            client.url("VOO;rm", 0, 1)


if __name__ == "__main__":
    unittest.main()
