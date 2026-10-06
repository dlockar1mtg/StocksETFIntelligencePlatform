"""Phase 4.4: near-duplicate clusters, best implementation, calls stay off without a passing gate,
and the governed package round-trip."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from foundation.market import provisional_package as P
from foundation.market import uip_package as U

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "uip" / "package_manifest.schema.json").read_text(encoding="utf-8"))


def months(n):
    return [f"{2023 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


class ClusterTests(unittest.TestCase):
    def test_complete_linkage_does_not_chain(self):
        rng = np.random.default_rng(5)
        ms = months(36)
        base = rng.normal(0.01, 0.04, 36)
        drift = rng.normal(0, 0.04, 36)
        returns = {"A": dict(zip(ms, base)), "B": dict(zip(ms, base + 0.0008 * drift)),
                   "C": dict(zip(ms, base + 0.0016 * drift)), "D": dict(zip(ms, base + 0.0024 * drift)),
                   "Z": dict(zip(ms, rng.normal(0.01, 0.04, 36)))}
        out = P.clusters(list(returns), returns, ms[-1])
        flat = [s for c in out for s in c]
        self.assertNotIn("Z", flat)
        self.assertEqual(len(flat), len(set(flat)))
        for cluster in out:                          # every pair inside a cluster meets the threshold
            for a in cluster:
                for b in cluster:
                    if a < b:
                        x = np.array([returns[a][m] for m in ms]); y = np.array([returns[b][m] for m in ms])
                        self.assertGreaterEqual(float(np.corrcoef(x, y)[0, 1]), 0.999)

    def test_best_implementation_prefers_official_cost(self):
        members = [{"symbol": "IVV", "annualized_3y": 0.2284, "expense_ratio": 0.0003},
                   {"symbol": "VOO", "annualized_3y": 0.2285, "expense_ratio": 0.0003},
                   {"symbol": "SPLG", "annualized_3y": 0.2283, "expense_ratio": 0.0002}]
        self.assertEqual(P.pick_best(members)["symbol"], "SPLG")
        members[2]["expense_ratio"] = None
        self.assertEqual(P.pick_best(members), {"symbol": "VOO", "basis": "HIGHEST_3Y_RETURN_NET_OF_COSTS"})


class PackageTests(unittest.TestCase):
    def test_round_trip_and_tamper_detection(self):
        records = [{"security_id": "SEC-US-VOO", "symbol": "VOO", "as_of_date": "2026-10-06", "close": 716.2,
                    "quality_status": "PROVISIONAL", "freshness_state": "CURRENT", "source_tier": 4}]
        validation, limits = U.package_validation(records, ["VOO", "SCHD", "QQQM"])
        self.assertEqual((validation, limits), ("PASS", []))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            files = {"funds.json": (b'{"funds": []}', 1), "latest_prices.csv": (U.latest_prices_csv(records).encode(), 1)}
            m = U.write_package(out, files=files, validation=validation, commit="6ed0688", generated_at_utc="2026-10-06T23:00:00+00:00",
                                as_of="2026-10-06", schema=SCHEMA, snapshot=b"s")
            self.assertEqual(m["domain"], "stocks_etf")
            self.assertEqual(m["certification_status"], "PROVISIONAL")
            self.assertFalse(m["automatic_execution_authorized"])
            U.verify_package(out, SCHEMA)
            (out / "funds.json").write_bytes(b"{}")
            with self.assertRaises(U.PackageError):
                U.verify_package(out, SCHEMA)

    def test_no_usable_seed_fails_the_package(self):
        records = [{"security_id": "SEC-US-VOO", "symbol": "VOO", "quality_status": "BLOCKED", "freshness_state": "UNKNOWN"}]
        self.assertEqual(U.package_validation(records, ["VOO"])[0], "FAIL")


if __name__ == "__main__":
    unittest.main()
