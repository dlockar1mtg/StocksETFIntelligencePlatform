"""Official expense ratios from the SEC risk/return summary data sets (Phase 4.3).

Parses each quarterly rr1 archive (sub.tsv for filing dates, num.tsv for values), keeps the
expense-ratio tags per SEC class ID, and builds a point-in-time history: at any date a class's
ratio is the one in its latest filing on or before that date. Classes are matched to the model
universe through the SEC's own class-to-ticker map, never by name.
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict

HISTORY_FIELDS = ("class_id", "series_id", "cik", "symbol", "security_id", "filed", "adsh", "form",
                  "net_expense_ratio", "gross_expense_ratio", "source_quarter")


def class_ticker_map(document: dict) -> dict[str, dict]:
    """company_tickers_mf.json -> {class_id: {cik, series_id, symbol}}."""
    fields = document["fields"]
    out = {}
    for row in document["data"]:
        r = dict(zip(fields, row))
        cls = str(r.get("classId") or "")
        if cls:
            out[cls] = {"cik": str(r.get("cik")), "series_id": str(r.get("seriesId") or ""), "symbol": str(r.get("symbol") or "").upper()}
    return out


def _tsv(archive: zipfile.ZipFile, name: str):
    member = next((n for n in archive.namelist() if n.lower().endswith(name)), None)
    if member is None:
        raise ValueError(f"archive has no {name}")
    with archive.open(member) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), delimiter="\t")


def parse_quarter(data: bytes, quarter: str, tags: dict[str, str], wanted_classes: set[str]) -> list[dict]:
    """Expense-ratio rows for the wanted classes from one rr1 archive."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    subs = {r["adsh"]: r for r in _tsv(archive, "sub.tsv")}
    by_tag = {v: k for k, v in tags.items()}
    found: dict[tuple[str, str], dict] = {}
    for r in _tsv(archive, "num.tsv"):
        tag = r.get("tag")
        if tag not in by_tag:
            continue
        cls = (r.get("class") or "").strip()
        if cls not in wanted_classes or (r.get("otherdims") or "").strip():
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError):
            continue
        if not 0 <= value < 0.2:                # an expense ratio above 20% a year is not a plausible fund fee
            continue
        key = (cls, r["adsh"])
        row = found.setdefault(key, {"class_id": cls, "series_id": (r.get("series") or "").strip(), "adsh": r["adsh"],
                                      "filed": (subs.get(r["adsh"], {}).get("filed") or "")[:8],
                                      "form": subs.get(r["adsh"], {}).get("form", ""), "source_quarter": quarter,
                                      "net_expense_ratio": "", "gross_expense_ratio": ""})
        row[by_tag[tag]] = f"{value:.6f}"
    return list(found.values())


def attach_identity(rows: list[dict], classes: dict[str, dict], universe_by_symbol: dict[str, str]) -> list[dict]:
    out = []
    for r in rows:
        ident = classes.get(r["class_id"], {})
        symbol = ident.get("symbol", "")
        out.append({**r, "cik": ident.get("cik", ""), "symbol": symbol, "security_id": universe_by_symbol.get(symbol, ""),
                    "series_id": r["series_id"] or ident.get("series_id", "")})
    return out


def history_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HISTORY_FIELDS, lineterminator="\n")
    writer.writeheader()
    for r in sorted(rows, key=lambda r: (r.get("symbol", ""), r.get("filed", ""), r.get("adsh", ""))):
        writer.writerow({k: r.get(k, "") for k in HISTORY_FIELDS})
    return buffer.getvalue()


def ratio_on(history: dict[str, list[tuple[str, float]]], symbol: str, date: str) -> float | None:
    """Net (else gross) expense ratio from the latest filing on or before date (YYYY-MM-DD)."""
    stamp = date.replace("-", "")
    best = None
    for filed, value in history.get(symbol, []):
        if filed <= stamp:
            best = value
        else:
            break
    return best


def load_history(path) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as handle:
        for r in csv.DictReader(handle):
            value = r["net_expense_ratio"] or r["gross_expense_ratio"]
            if r["symbol"] and value and r["filed"]:
                out[r["symbol"]].append((r["filed"], float(value)))
    for v in out.values():
        v.sort()
    return dict(out)
