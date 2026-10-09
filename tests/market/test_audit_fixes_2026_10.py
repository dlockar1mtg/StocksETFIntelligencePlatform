"""Fixes from the 2026-10-09 system audit (synthetic data only): peer-group rules and stable live groups,
reference-trust fees in projections, the backup-run gate, SEC zero-row warnings, when-to-buy scope,
call hysteresis and bands from config, and the partial-failure check."""
from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from foundation.market import provisional_full_coverage as FC
from foundation.market import provisional_package as P
from foundation.market import provisional_peer_groups as G
from foundation.market import provisional_projection as PJ
from foundation.market import provisional_ranking as R
from foundation.market import sec_expense_ratios as X
from tests.market.test_provisional_projection import fund

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_provisional_etf_package as B  # noqa: E402
import etf_backup_gate as GATE  # noqa: E402
import run_hosted_etf_market_data as RUN  # noqa: E402

RANKING_POLICY = json.loads((ROOT / "config" / "market" / "provisional_ranking_policy.json").read_text(encoding="utf-8"))
HOLIDAYS = set(json.loads((ROOT / "config" / "market" / "hosted_market_data_policy.json").read_text(encoding="utf-8"))["nyse_holidays"]["dates"])


def months(n, start=2021):
    return [f"{start + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]


class Universe:
    """Independent reference series with realistic relative volatilities, plus helpers to add funds."""

    def __init__(self, n=48, seed=11):
        self.rng = np.random.default_rng(seed)
        self.ms = months(n)
        vol = {r: 0.045 for r in G.REFERENCE_GROUP}
        vol.update({"BIL": 0.0005, "SHY": 0.004, "IEF": 0.015, "TLT": 0.035, "TIP": 0.012, "MUB": 0.012, "LQD": 0.02, "HYG": 0.02})
        rates = self.rng.normal(0, 1, n)                         # one rate factor drives the Treasury ladder
        self.base = {}
        for r in G.REFERENCE_GROUP:
            own = self.rng.normal(0, 1, n)
            mix = 0.97 * rates + 0.24 * own if r in ("SHY", "IEF", "TLT") else own
            self.base[r] = 0.005 + vol[r] * mix
        # the S&P 500 and its style halves move together, as they do
        self.base["VUG"] = self.base["SPY"] + 0.02 * self.rng.normal(0, 1, n)
        self.base["VTV"] = self.base["SPY"] + 0.02 * self.rng.normal(0, 1, n)
        self.returns = {r: dict(zip(self.ms, v)) for r, v in self.base.items()}

    def add(self, symbol, series):
        self.returns[symbol] = dict(zip(self.ms, np.asarray(series, dtype=float)))
        return np.asarray(series, dtype=float)

    def noise(self, sd):
        return self.rng.normal(0, sd, len(self.ms))

    def group(self, symbol, end=None):
        return G.classify_all(self.returns, [symbol], end or self.ms[-1])[symbol]


class PeerGroupAuditTests(unittest.TestCase):
    def setUp(self):
        self.u = Universe()

    def test_leveraged_fund_with_low_reference_correlation_is_caught_through_its_twin(self):
        u = self.u
        semis = u.add("SEMI", 1.4 * u.base["XLK"] + u.noise(0.04))          # 1x semiconductors: corr ~0.85 with XLK
        u.add("SEMI3", 3 * semis)
        old_rule_correlation = G._corr(np.array(list(u.returns["SEMI3"].values())), u.base["XLK"])
        self.assertLess(old_rule_correlation, 0.9)                          # the old test needed >= 0.9
        g = u.group("SEMI3")
        self.assertEqual(g["group"], "SPECIALIZED_LEVERAGED")
        self.assertEqual(u.group("SEMI")["group"], "US_SECTOR_TECHNOLOGY")   # high natural beta is not leverage

    def test_inverse_comes_from_the_market_beta_and_the_twins(self):
        u = self.u
        bio = u.add("BIO", 1.2 * u.base["SPY"] + u.noise(0.06))
        u.add("BIO3", 3 * bio)
        u.add("BIOBEAR", -3 * bio)
        self.assertEqual(u.group("BIOBEAR")["group"], "SPECIALIZED_INVERSE")
        self.assertEqual(u.group("BIO3")["group"], "SPECIALIZED_LEVERAGED")
        self.assertNotIn(u.group("BIO")["group"], ("SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE"))

    def test_partial_copies_of_the_market_are_not_an_unlevered_base(self):
        u = self.u
        for k in range(3):
            u.add(f"SP{k}", u.base["SPY"] + u.noise(0.001))
        u.add("BUFFER", 0.5 * u.base["SPY"] + u.noise(0.002))               # a 50/50 or buffer fund
        self.assertEqual(u.group("SP0")["group"], "US_EQUITY_LARGE_BLEND")

    def test_total_market_fund_is_blend_whatever_its_small_tilt(self):
        u = self.u
        tilt = u.base["VTV"] - u.base["VUG"]
        u.add("TOTAL", u.base["SPY"] + 0.2 * tilt + u.noise(0.001))
        g = u.group("TOTAL")
        self.assertGreaterEqual(g["correlation"], 0.99)
        self.assertEqual(g["group"], "US_EQUITY_LARGE_BLEND")

    def test_treasury_ladder_between_shy_and_ief_is_not_leveraged_but_3x_long_bonds_are(self):
        u = self.u
        u.add("LADDER", 0.4 * u.base["IEF"] + 0.8 * u.base["SHY"] + u.noise(0.0003))
        g = u.group("LADDER")
        self.assertGreaterEqual(G._ols_beta(np.array(list(u.returns["LADDER"].values())), u.base["SHY"]), 1.6)
        self.assertTrue(g["group"].startswith("BOND_"), g)
        u.add("TMF", 3 * u.base["TLT"])
        self.assertEqual(u.group("TMF")["group"], "SPECIALIZED_LEVERAGED")

    def test_sector_group_needs_a_dominant_style_share(self):
        u = self.u
        # a low-volatility dividend fund: correlates with REITs, but REITs are a minority of its mix
        u.base["VNQ"] = 0.6 * u.base["VTV"] + 0.8 * u.noise(0.045) + 0.005
        u.returns["VNQ"] = dict(zip(u.ms, u.base["VNQ"]))
        u.add("LOWVOL", 0.38 * u.base["VNQ"] + 0.12 * u.base["VTV"] + 0.2 * u.base["XLP"] + u.noise(0.002))
        g = u.group("LOWVOL")
        self.assertEqual(g.get("sector_candidate"), "VNQ")
        self.assertLess(g["style_share"], 0.6)
        self.assertNotEqual(g["group"], "REAL_ESTATE")
        self.assertTrue(g["group"].startswith("US_EQUITY"), g)
        u.add("REIT", u.base["VNQ"] + u.noise(0.003))
        self.assertEqual(u.group("REIT")["group"], "REAL_ESTATE")

    def test_live_groups_use_the_prior_december_and_new_funds_on_arrival(self):
        u = self.u
        self.assertEqual(G.anchor_month("2026-09"), "2025-12")
        self.assertEqual(G.anchor_month("2026-12"), "2026-12")
        u.add("TRK", u.base["EFA"] + u.noise(0.002))
        end = u.ms[-1]                                                       # 2024-12 -> use a mid-year month
        mid = u.ms[-4]                                                       # 2024-09
        live = G.live_groups(u.returns, ["TRK"], mid)
        self.assertEqual(live["TRK"]["classified_at"], G.anchor_month(mid))
        # changing the months after the anchor December does not move the live group
        before = dict(live["TRK"])
        for m in u.ms[-12:]:
            if m > G.anchor_month(mid):
                u.returns["TRK"][m] = u.returns["EEM"][m]
        self.assertEqual(G.live_groups(u.returns, ["TRK"], mid)["TRK"]["group"], before["group"])
        # a fund too young at the anchor is classified on arrival and kept until the next December
        young = {m: v for m, v in u.returns["EFA"].items() if m >= u.ms[-26]}
        u.returns["NEW"] = young
        first = G.live_groups(u.returns, ["NEW"], u.ms[-3])["NEW"]
        self.assertEqual(first["classified_at"], u.ms[-3])
        self.assertEqual(first["group"], "INTL_DEVELOPED_EQUITY")
        kept = G.live_groups(u.returns, ["NEW"], u.ms[-2], {"NEW": {**first, "group": "KEPT_FOR_TEST"}})["NEW"]
        self.assertEqual(kept["group"], "KEPT_FOR_TEST")
        self.assertTrue(end)

    def test_grouping_version_is_published(self):
        self.assertTrue(G.GROUPING_VERSION.startswith("2026-10-09"))
        self.assertEqual(RANKING_POLICY["taxonomy"]["grouping_version"], G.GROUPING_VERSION)
        self.assertEqual(RANKING_POLICY["policy_version"], "1.1.0")
        last = RANKING_POLICY["amendments"][-2]
        self.assertTrue(last["after_results"])
        self.assertEqual(last["on"], "2026-10-09")


class ProjectionFeeTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        ms = [f"{2000 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(240)]
        spy = rng.normal(0.008, 0.045, 240)
        self.ms = ms
        self.features = {"SPY": fund(spy, ms), "BIL": fund(np.full(240, 0.002), ms, 0.03),
                         "SHY": fund(np.full(240, 0.0025), ms, 0.035), "TRK": fund(spy + rng.normal(0, 0.002, 240), ms)}
        self.group = {"group": "US_EQUITY_LARGE_BLEND", "nearest_reference": "SPY"}

    def test_reference_trust_fee_is_used_when_the_sec_has_none(self):
        fees = {"TRK": 0.0020}                                               # SPY has no SEC fee
        p = PJ.Projector(self.features, lambda s, d: fees.get(s)).project("TRK", self.group, self.ms[-1])
        self.assertEqual(p["fee_gap_status"], "KNOWN")
        self.assertAlmostEqual(p["fee_gap"], 0.0020 - PJ.REFERENCE_TRUST_FEES["SPY"], delta=1e-5)
        free = PJ.Projector(self.features, lambda s, d: {"TRK": PJ.REFERENCE_TRUST_FEES["SPY"]}.get(s)).project("TRK", self.group, self.ms[-1])
        self.assertLess(p["p50"], free["p50"])                               # the dearer fund projects lower

    def test_unknown_fee_is_marked_not_zero(self):
        p = PJ.Projector(self.features, lambda s, d: None).project("TRK", self.group, self.ms[-1])
        self.assertIsNone(p["fee_gap"])
        self.assertEqual(p["fee_gap_status"], "UNKNOWN")

    def test_the_table_only_fills_gaps(self):
        pj = PJ.Projector(self.features, lambda s, d: 0.0009 if s == "SPY" else None)
        self.assertEqual(pj.fee("SPY", "2026-09-28"), 0.0009)                # an SEC value wins
        self.assertEqual(PJ.Projector(self.features).fee("GLD", "2026-09-28"), 0.0040)
        self.assertEqual(set(PJ.REFERENCE_TRUST_FEES), {"SPY", "GLD", "SLV", "DBC", "USO"})


class BackupGateTests(unittest.TestCase):
    def status(self, days):
        return {"funds": [{"symbol": f"F{i}", "as_of_date": d, "freshness_state": "CURRENT"} for i, d in enumerate(days)]}

    def test_stored_current_labels_are_not_trusted(self):
        now = datetime(2026, 10, 9, 1, 20, tzinfo=timezone.utc)              # Thursday 21:20 New York
        self.assertEqual(GATE.S.last_session(now, HOLIDAYS), "2026-10-08")
        run, session, share = GATE.decide(self.status(["2026-10-07"] * 100), now, HOLIDAYS)
        self.assertTrue(run)
        self.assertEqual(share, 0.0)
        run, _, _ = GATE.decide(self.status(["2026-10-08"] * 91 + ["2026-10-07"] * 9), now, HOLIDAYS)
        self.assertFalse(run)
        run, _, _ = GATE.decide(self.status(["2026-10-08"] * 89 + ["2026-10-07"] * 11), now, HOLIDAYS)
        self.assertTrue(run)

    def test_weekends_and_holidays(self):
        saturday = datetime(2026, 10, 10, 4, 20, tzinfo=timezone.utc)
        self.assertEqual(GATE.decide(self.status(["2026-10-09"] * 10), saturday, HOLIDAYS)[1], "2026-10-09")
        after_thanksgiving = datetime(2026, 11, 27, 1, 20, tzinfo=timezone.utc)   # 26 Nov is a holiday
        self.assertEqual(GATE.decide(self.status([]), after_thanksgiving, HOLIDAYS)[1], "2026-11-25")
        self.assertTrue(GATE.decide(self.status([]), after_thanksgiving, HOLIDAYS)[0])

    def test_workflow_reads_the_status_raw_and_uses_the_gate(self):
        wf = (ROOT / ".github" / "workflows" / "etf-hosted-market-data.yml").read_text(encoding="utf-8")
        self.assertIn("application/vnd.github.raw", wf)
        self.assertIn("scripts/etf_backup_gate.py", wf)
        self.assertNotIn("freshness_summary\") or {}", wf)


class SecZeroRowTests(unittest.TestCase):
    TAGS = {"net_expense_ratio": "NetExpensesOverAssets", "gross_expense_ratio": "ExpensesOverAssets"}

    def archive(self, rows):
        sub = "adsh\tcik\tname\tform\tfiled\n0001-25-1\t36405\tV\t485BPOS\t20250815\n"
        num = "adsh\ttag\tversion\tddate\tuom\tseries\tclass\tmeasure\tdocument\totherdims\tiprx\tvalue\n" + "".join(rows)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("sub.tsv", sub)
            z.writestr("num.tsv", num)
        return buf.getvalue()

    def test_an_empty_quarter_explains_itself(self):
        data = self.archive(["0001-25-1\tNetExpensesOverAssets\toef/2025\t20250815\tpure\tS1\t\t\t\tFundAxis=S1;Other=X\t0\t0.0003\n"])
        diag = {}
        self.assertEqual(X.parse_quarter(data, "2025q3", self.TAGS, {"C000092055"}, diag), [])
        self.assertEqual((diag["expense_facts"], diag["without_class"], diag["filings_kept"]), (1, 1, 0))
        self.assertEqual(diag["versions"], {"oef/2025": 1})

    def test_class_carried_as_the_only_dimension_is_read(self):
        data = self.archive(["0001-25-1\tNetExpensesOverAssets\toef/2025\t20250815\tpure\tS1\t\t\t\tClassAxis=C000092055Member\t0\t0.0003\n"])
        diag = {}
        rows = X.parse_quarter(data, "2025q3", self.TAGS, {"C000092055"}, diag)
        self.assertEqual([r["class_id"] for r in rows], ["C000092055"])
        self.assertEqual(diag["class_from_dimension"], 1)

    def test_package_limitation_while_recent_quarters_are_empty(self):
        summary = {"quarters": {"2025q1": 410, "2025q2": 102, "2025q3": 0, "2025q4": 0, "2026q1": 0, "2026q2": 0, "2026q3": "NOT_PUBLISHED"}}
        limits = B.sec_fee_limitations(summary, "20250512")
        self.assertEqual(len(limits), 1)
        self.assertIn("2025q3, 2025q4, 2026q1, 2026q2", limits[0])
        self.assertIn("20250512", limits[0])
        self.assertEqual(B.sec_fee_limitations({"quarters": {"2025q1": 410, "2025q2": 102}}), [])

    def test_stale_limitation_text_is_gone(self):
        text = " ".join(RANKING_POLICY["known_limitations"])
        self.assertNotIn("no expense ratios", text)


class WhenToBuyScopeTests(unittest.TestCase):
    def test_family_rule_only_for_the_groups_its_index_is_built_from(self):
        for g in ("PRECIOUS_METALS", "COMMODITIES", "REAL_ESTATE", "US_EQUITY_LARGE_BLEND", "BOND_HIGH_YIELD"):
            self.assertTrue(P.timing_applies(g), g)
        for g in ("IDIOSYNCRATIC", "SPECIALIZED_LEVERAGED", "SPECIALIZED_INVERSE", "SOMETHING_ELSE"):
            self.assertFalse(P.timing_applies(g), g)

    def test_idiosyncratic_fund_near_a_real_asset_reference_gets_no_rule_verdict(self):
        wait = {"rule": "WAIT_FOR_DIP", "parameter": 0.2, "verdict": "WAIT"}
        steady = {"rule": None, "verdict": "STEADY_BUYING"}
        recs = [{"symbol": "FXI", "usage": "MODEL", "peer_group": "IDIOSYNCRATIC", "expense_ratio": 0.005,
                 "group_evidence": {"nearest_reference": "DBC", "correlation": 0.3}},
                {"symbol": "IDX", "usage": "MODEL", "peer_group": "IDIOSYNCRATIC", "expense_ratio": 0.005,
                 "group_evidence": {"nearest_reference": "SPY", "correlation": 0.7}}]
        FC.add_full_coverage(recs, {"COMMODITIES": {"when_to_buy": wait}}, {}, "2026-09", None,
                             timing_reading=lambda fam: steady if fam == "US_EQUITY" else wait)
        self.assertIsNone(recs[0].get("when_to_buy"))
        self.assertEqual(recs[1]["when_to_buy"]["verdict"], "STEADY_BUYING")
        self.assertTrue(recs[1]["when_to_buy"]["loose"])


class CallTests(unittest.TestCase):
    def test_bands_come_from_the_policy(self):
        self.assertEqual(P.CALL_BANDS, RANKING_POLICY["calls"]["bands_percentile"])

    def build(self, previous):
        u = Universe(n=48, seed=5)
        ms = u.ms
        feats = {}
        for sym, rets in u.base.items():
            feats[sym] = fund(rets, ms)
        clones = ["C1", "C2", "C3", "C4", "C5"]
        for c in clones:
            feats[c] = fund(u.base["SPY"] + u.noise(0.0005), ms)
        fees = dict(zip(clones, (0.0009, 0.0003, 0.0005, 0.0007, 0.0001)))       # C2 is second cheapest: percentile 75
        status = {"funds": [{"security_id": f"SEC-US-{c}", "symbol": c, "usage": "MODEL", "quality_status": "PROVISIONAL",
                             "freshness_state": "CURRENT", "as_of_date": "2024-12-31", "close": 1.0} for c in clones]}
        research = {"gate": {}, "cost_test": {"calls_enabled": True}, "timing": {}}
        records, _ = P.build_records(status=status, features=feats, research=research, cached_bars=lambda s: [],
                                     expense_ratio=fees.get, previous=previous)
        return {r["symbol"]: r for r in records}

    def test_a_buy_at_percentile_75_stays_buy(self):
        fresh = self.build({})
        self.assertEqual(fresh["C2"]["peer_group"], "US_EQUITY_LARGE_BLEND")
        self.assertEqual(fresh["C2"]["cost_percentile_in_group"], 75.0)
        self.assertEqual(fresh["C2"]["ranking_call"], "ACCUMULATE")
        kept = self.build(P.previous_state({"funds": [{"symbol": "C2", "ranking_call": "BUY", "peer_group": "US_EQUITY_LARGE_BLEND",
                                                        "group_evidence": {}}]}))
        self.assertEqual(kept["C2"]["ranking_call"], "BUY")
        self.assertEqual(R.assign_call(75, "BUY", P.CALL_BANDS), "BUY")
        self.assertIsNone(P.previous_state({"funds": [{"symbol": "C2", "peer_group": "X", "group_evidence": {}}]})["C2"]["group"])
        same = P.previous_state({"grouping_version": G.GROUPING_VERSION, "funds": [{"symbol": "C2", "peer_group": "X", "group_evidence": {}}]})
        self.assertEqual(same["C2"]["group"]["group"], "X")          # groups carry over only under the same rules
        self.assertEqual(R.assign_call(65, "BUY", P.CALL_BANDS), "ACCUMULATE")


class AcceptedShareTests(unittest.TestCase):
    def test_warn_below_95_fail_below_80(self):
        def recs(ok, total=100):
            return [{"accepted_this_run": i < ok} for i in range(total)]
        self.assertEqual(RUN.accepted_check(recs(97))[0::2], (0, ""))
        code, share, msg = RUN.accepted_check(recs(90))
        self.assertEqual((code, share), (0, 0.9))
        self.assertTrue(msg.startswith("::warning"))
        code, _, msg = RUN.accepted_check(recs(70))
        self.assertEqual(code, 1)
        self.assertTrue(msg.startswith("::error"))
        self.assertEqual((RUN.WARN_ACCEPTED_SHARE, RUN.FAIL_ACCEPTED_SHARE), (0.95, 0.80))


if __name__ == "__main__":
    unittest.main()
