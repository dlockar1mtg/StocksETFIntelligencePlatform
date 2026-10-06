"""Phase 4.3: official expense ratios from SEC risk/return data, matched by class ID, point in time."""
from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from foundation.market import sec_expense_ratios as X

TAGS = {"net_expense_ratio": "NetExpensesOverAssets", "gross_expense_ratio": "ExpensesOverAssets"}


def archive() -> bytes:
    sub = "adsh\tcik\tname\tform\tfiled\n0001-26-1\t36405\tVANGUARD\t485BPOS\t20260415\n0001-26-2\t1\tX\t485BPOS\t20260416\n"
    num = ("adsh\ttag\tversion\tddate\tuom\tseries\tclass\tmeasure\tdocument\totherdims\tiprx\tvalue\n"
           "0001-26-1\tNetExpensesOverAssets\trr\t20260415\tpure\tS000002839\tC000092055\t\t\t\t0\t0.0003\n"
           "0001-26-1\tExpensesOverAssets\trr\t20260415\tpure\tS000002839\tC000092055\t\t\t\t0\t0.0003\n"
           "0001-26-1\tNetExpensesOverAssets\trr\t20260415\tpure\tS000002839\tC000092055\t\t\tAxis=Member\t0\t0.0100\n"
           "0001-26-2\tNetExpensesOverAssets\trr\t20260416\tpure\tS9\tC999\t\t\t\t0\t0.0050\n"
           "0001-26-2\tNetExpensesOverAssets\trr\t20260416\tpure\tS9\tC000000001\t\t\t\t0\t5.0\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("sub.tsv", sub)
        z.writestr("num.tsv", num)
    return buf.getvalue()


class ExpenseRatioTests(unittest.TestCase):
    def test_parses_wanted_classes_only_without_dimensions(self):
        rows = X.parse_quarter(archive(), "2026q2", TAGS, {"C000092055", "C000000001"})
        self.assertEqual(len(rows), 1)                      # C999 not wanted; 5.0 is implausible
        r = rows[0]
        self.assertEqual((r["net_expense_ratio"], r["gross_expense_ratio"], r["filed"]), ("0.000300", "0.000300", "20260415"))

    def test_identity_comes_from_the_sec_class_map(self):
        classes = X.class_ticker_map({"fields": ["cik", "seriesId", "classId", "symbol"],
                                      "data": [[36405, "S000002839", "C000092055", "voo"]]})
        rows = X.attach_identity(X.parse_quarter(archive(), "2026q2", TAGS, set(classes)), classes, {"VOO": "SEC-US-VOO"})
        self.assertEqual((rows[0]["symbol"], rows[0]["security_id"]), ("VOO", "SEC-US-VOO"))

    def test_point_in_time_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.csv"
            rows = [{"class_id": "C1", "symbol": "VOO", "filed": "20200101", "net_expense_ratio": "0.0004", "gross_expense_ratio": ""},
                    {"class_id": "C1", "symbol": "VOO", "filed": "20250101", "net_expense_ratio": "0.0003", "gross_expense_ratio": ""}]
            path.write_text(X.history_csv(rows), encoding="utf-8")
            h = X.load_history(path)
            self.assertIsNone(X.ratio_on(h, "VOO", "2019-06-30"))
            self.assertEqual(X.ratio_on(h, "VOO", "2024-06-30"), 0.0004)
            self.assertEqual(X.ratio_on(h, "VOO", "2026-01-31"), 0.0003)


if __name__ == "__main__":
    unittest.main()
