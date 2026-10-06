"""Daily ETF market data: parsing, total-return reconciliation, quarantine and governed observations."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from foundation.market_data import series as S
from foundation.validation.provider_contracts import validate_observation
from scripts import collect_etf_market_data as C

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config" / "market" / "monitored_funds.json").read_text(encoding="utf-8"))
CONTROL = json.loads((ROOT / "config" / "providers" / "provider_contracts.json").read_text(encoding="utf-8"))
HOLIDAYS = set(CONFIG["nyse_holidays"]["dates"])
NOW = datetime(2026, 10, 6, 22, 30, tzinfo=timezone.utc)      # 18:30 New York, after the close


def sessions(end: str, count: int) -> list[str]:
    out, day = [], date.fromisoformat(end)
    while len(out) < count:
        if day.weekday() < 5 and day.isoformat() not in HOLIDAYS:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return sorted(out)


def payload(ticker="VOO", n=900, end="2026-10-06", dividend_every=63, dividend=1.5, split_at=None, bad_adj_day=None, cut=None):
    days = sessions(end, n)
    closes = [400 * (1.0004 ** i) * (1 + 0.01 * ((i % 7) - 3) / 3) for i in range(n)]
    divs = {days[i]: dividend for i in range(dividend_every, n, dividend_every)}
    adj = closes[:]
    for i in range(n - 1, 0, -1):                                # Yahoo-style multiplicative adjustment
        if days[i] in divs:
            factor = 1 - divs[days[i]] / closes[i - 1]
            for j in range(i):
                adj[j] *= factor
    if bad_adj_day is not None:
        adj[bad_adj_day] *= 1.05
    stamp = lambda d: int(datetime.fromisoformat(d + "T14:30:00+00:00").timestamp())
    events = {"dividends": {str(stamp(d)): {"amount": a, "date": stamp(d)} for d, a in divs.items()}}
    if split_at:
        events["splits"] = {str(stamp(split_at)): {"date": stamp(split_at), "numerator": 2, "denominator": 1}}
    if cut:
        keep = sum(1 for d in days if d <= cut)
        days, closes, adj = days[:keep], closes[:keep], adj[:keep]
        events["dividends"] = {k: v for k, v in events["dividends"].items() if datetime.fromtimestamp(v["date"], timezone.utc).date().isoformat() <= cut}
        n = keep
    return {"chart": {"result": [{
        "meta": {"symbol": ticker, "currency": "USD"},
        "timestamp": [stamp(d) for d in days], "events": events,
        "indicators": {"quote": [{"close": closes, "volume": [1000] * n}], "adjclose": [{"adjclose": adj}]},
    }], "error": None}}


class SeriesTests(unittest.TestCase):
    def test_parse_drops_unsettled_today(self):
        early = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)   # 11:00 New York
        parsed = S.parse_yahoo_chart(payload(), "VOO", now_utc=early)
        self.assertEqual(parsed.bars[-1].day, "2026-10-05")
        self.assertEqual(S.parse_yahoo_chart(payload(), "VOO", now_utc=NOW).bars[-1].day, "2026-10-06")

    def test_rejects_wrong_symbol_and_currency(self):
        with self.assertRaises(S.SeriesError):
            S.parse_yahoo_chart(payload(ticker="SPY"), "VOO", now_utc=NOW)
        bad = payload()
        bad["chart"]["result"][0]["meta"]["currency"] = "EUR"
        with self.assertRaises(S.SeriesError):
            S.parse_yahoo_chart(bad, "VOO", now_utc=NOW)

    def test_total_return_reinvests_at_ex_date_close_and_reconciles(self):
        parsed = S.parse_yahoo_chart(payload(), "VOO", now_utc=NOW)
        S.reconstruct_total_return(parsed.bars)
        ex = next(i for i, b in enumerate(parsed.bars) if b.dividend)
        b, p = parsed.bars[ex], parsed.bars[ex - 1]
        self.assertAlmostEqual(b.tr_index / p.tr_index, (b.close + b.dividend) / p.close, places=5)
        report = S.reconcile_with_provider(parsed.bars, CONFIG["reconciliation"])
        self.assertEqual(report["status"], "PASS", report)

    def test_bad_adjusted_close_fails_reconciliation(self):
        parsed = S.parse_yahoo_chart(payload(bad_adj_day=850), "VOO", now_utc=NOW)
        S.reconstruct_total_return(parsed.bars)
        self.assertEqual(S.reconcile_with_provider(parsed.bars, CONFIG["reconciliation"])["status"], "FAIL")

    def test_cross_check_and_freshness(self):
        parsed = S.parse_yahoo_chart(payload(), "VOO", now_utc=NOW)
        good = {b.day: b.close * 1.001 for b in parsed.bars}
        self.assertEqual(S.cross_check(parsed.bars, good, 5, 0.005)["status"], "PASS")
        self.assertEqual(S.cross_check(parsed.bars, {k: v * 1.02 for k, v in good.items()}, 5, 0.005)["status"], "FAIL")
        self.assertEqual(S.cross_check(parsed.bars, {}, 5, 0.005)["status"], "UNAVAILABLE")
        rules = CONFIG["freshness"]
        self.assertEqual(S.last_session(NOW, HOLIDAYS), "2026-10-06")
        self.assertEqual(S.freshness_state("2026-10-06", "2026-10-06", HOLIDAYS, rules), "CURRENT")
        self.assertEqual(S.freshness_state("2026-10-05", "2026-10-06", HOLIDAYS, rules), "AGING")
        self.assertEqual(S.freshness_state("2026-09-28", "2026-10-06", HOLIDAYS, rules), "STALE")
        self.assertEqual(S.last_session(datetime(2026, 11, 27, 12, tzinfo=timezone.utc), HOLIDAYS), "2026-11-25")

    def test_split_explains_revised_history(self):
        old = S.parse_yahoo_chart(payload(cut="2026-08-25"), "VOO", now_utc=NOW)
        S.reconstruct_total_return(old.bars)
        stored = S.read_csv(S.to_csv(old.bars))
        new = S.parse_yahoo_chart(payload(), "VOO", now_utc=NOW)
        for b in new.bars:
            b.close /= 2
        self.assertFalse(S.revisions(stored, new.bars, {}, 0.0005, "2023-01-01")["ok"])
        self.assertTrue(S.revisions(stored, new.bars, {"2026-09-01": 2.0}, 0.0005, "2023-01-01")["ok"])


class CollectorTests(unittest.TestCase):
    def run_fund(self, store, chart, stooq=None):
        fund = CONFIG["funds"][0]
        provider = {**CONFIG["providers"][0], "best_quality": "PROVISIONAL"}
        return C.process_fund(fund, provider, CONFIG["reconciliation"], CONFIG["freshness"], HOLIDAYS, NOW,
                              store, store, store / "quarantine", yahoo=lambda t, n: chart,
                              stooq=lambda s: stooq or {})

    def test_accepted_fund_is_a_valid_provisional_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self.run_fund(Path(tmp), payload())
            self.assertTrue(record["accepted_this_run"], record["failures"])
            self.assertEqual(record["quality_status"], "PROVISIONAL")
            self.assertEqual(record["freshness_state"], "CURRENT")
            self.assertEqual(record["payload"]["distribution_count_trailing_12m"], 4)
            validate_observation(CONTROL, record, now=NOW)
            self.assertTrue((Path(tmp) / "prices" / "VOO.csv").exists())
            self.assertIn("single-source", " ".join(record["limitations"]))

    def test_failed_reconciliation_quarantines_and_keeps_stored_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            self.run_fund(store, payload(cut="2026-09-15"))
            kept = (store / "prices" / "VOO.csv").read_text()
            record = self.run_fund(store, payload(bad_adj_day=850))
            self.assertEqual(record["quality_status"], "QUARANTINED")
            self.assertEqual((store / "prices" / "VOO.csv").read_text(), kept)
            self.assertTrue((store / "quarantine" / "VOO.csv").exists())
            self.assertEqual(record["as_of_date"], "2026-09-15")
            self.assertEqual(record["freshness_state"], "STALE")

    def test_fetch_failure_without_history_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            fund = CONFIG["funds"][0]
            provider = {**CONFIG["providers"][0], "best_quality": "PROVISIONAL"}

            def boom(t, n):
                raise RuntimeError("connect rejected")
            record = C.process_fund(fund, provider, CONFIG["reconciliation"], CONFIG["freshness"], HOLIDAYS, NOW,
                                    Path(tmp), Path(tmp), Path(tmp) / "q", yahoo=boom, stooq=lambda s: {})
            self.assertEqual(record["quality_status"], "BLOCKED")
            self.assertEqual(record["freshness_state"], "UNKNOWN")


class GovernanceTests(unittest.TestCase):
    def test_free_sources_never_certify(self):
        for provider in CONFIG["providers"]:
            self.assertGreaterEqual(provider["source_tier"], 3)
            self.assertEqual(CONFIG["best_quality_state_for_tier"][str(provider["source_tier"])], "PROVISIONAL")
        self.assertFalse(CONFIG["certified_market_monitoring_authorized"])
        self.assertFalse(CONFIG["automatic_execution_authorized"])

    def test_funds_have_stable_identities_and_the_seed_universe_is_unchanged(self):
        tickers = [f["ticker"] for f in CONFIG["funds"]]
        self.assertEqual(len(tickers), len(set(tickers)))
        for fund in CONFIG["funds"]:
            self.assertEqual(fund["security_id"], f"SEC-US-{fund['ticker']}")
        held = {f["ticker"] for f in CONFIG["funds"] if f["usage"] == "HELD"}
        self.assertEqual(held, {"VOO", "SCHD", "QQQM", "QQQ", "IWM", "DIA", "EDOW", "IYY"})
        seed = json.loads((ROOT / "config" / "universe" / "initial_etf_universe.json").read_text(encoding="utf-8"))
        self.assertEqual([s["ticker"] for s in seed["securities"]], ["VOO", "SCHD", "QQQM"])


if __name__ == "__main__":
    unittest.main()
