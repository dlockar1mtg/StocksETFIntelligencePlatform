"""Phase 4.4: build the provisional ETF universe package for the UIP.

Usage: python scripts/build_provisional_etf_package.py [--output exports/etf/package]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market import hosted_market_data as H  # noqa: E402
from foundation.market import provisional_package as P  # noqa: E402
from foundation.market import provisional_projection as PJ  # noqa: E402
from foundation.market import provisional_ranking as R  # noqa: E402
from foundation.market import sec_expense_ratios as X  # noqa: E402
from foundation.market import uip_package as U  # noqa: E402

DATA = ROOT / "data" / "curated" / "hosted_etf"
SCHEMA = ROOT / "contracts" / "uip" / "package_manifest.schema.json"
MARKET = ROOT / "config" / "market" / "hosted_market_data_policy.json"
RANKING = ROOT / "config" / "market" / "provisional_ranking_policy.json"


def commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0000000"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "exports" / "etf" / "package")
    args = parser.parse_args(argv)
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
    market, ranking, schema = load(MARKET), load(RANKING), load(SCHEMA)
    status = load(DATA / "market_data_status.json")
    research = load(DATA / "research" / "provisional_ranking_research.json")
    features = R.load_features(DATA / "month_end_features.csv")
    cache = ROOT / market["storage"]["daily_cache_dir"]
    history_path = DATA / "expense_ratio_history.csv"
    history = X.load_history(history_path) if history_path.exists() else {}
    today = datetime.now(timezone.utc).date().isoformat()
    expense = (lambda s: X.ratio_on(history, s, today)) if history else None
    projection_path = DATA / "research" / "provisional_projection_research.json"
    projection = load(projection_path) if projection_path.exists() else None
    projector = PJ.Projector(features, (lambda s, d: X.ratio_on(history, s, d)) if history else None) if projection else None
    coverage_path = DATA / "research" / "provisional_full_coverage_research.json"
    coverage = load(coverage_path) if coverage_path.exists() else None
    records, groups = P.build_records(status=status, features=features, research=research,
                                      cached_bars=lambda s: H.read_cached_bars(cache, s) if cache.exists() else [],
                                      expense_ratio=expense, projector=projector, projection=projection, full_coverage=coverage)
    validation, limitations = U.package_validation(records, market["universe"]["required_seed_symbols"])
    as_of = max((r.get("as_of_date") or "" for r in records), default=today) or today
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    research_doc = {"policy_id": ranking["policy_id"], "generated_at_utc": research["generated_at_utc"], "gate": research["gate"],
                    "ranking_12m": research["walk_forward"]["12m"]["results"].get("ALL"),
                    "ranking_36m": research["walk_forward"]["36m"]["results"].get("ALL"),
                    "factor_ic_12m": research["walk_forward"]["12m"]["factor_ic_full_sample"],
                    "factor_ic_36m": research["walk_forward"]["36m"]["factor_ic_full_sample"],
                    "timing": research["timing"], "cost_test": research.get("cost_test"), "known_limitations": research["known_limitations"],
                    "amendments": ranking.get("amendments", []), "owner_authorization": ranking["owner_authorization"],
                    "projection_test": None if not projection else {
                        "policy_id": projection["policy_id"], "generated_at_utc": projection.get("generated_at_utc"),
                        "observations": projection["observations"], "test_starts": projection["test_starts"],
                        "overall": projection["overall"], "families": projection["families"],
                        "family_status": projection.get("family_status"), "rules_now": projection["rules_now"],
                        "passes_registered_test": projection["passes"],
                        "by_start_year": {str(y): {"n": c.get("n"), "inside_10_90": c.get("inside_10_90")} for y, c in projection["by_start_year"].items()},
                        "amendments": load(ROOT / "config" / "market" / "provisional_projection_policy.json").get("amendments", [])},
                    "full_coverage_test": None if not coverage else {
                        "policy_id": coverage["policy_id"], "generated_at_utc": coverage.get("generated_at_utc"),
                        "observations": coverage["observations"], "test_starts": coverage["test_starts"],
                        "categories": coverage["categories"], "category_status": coverage["category_status"]}}
    funds_doc = {"package_format": U.PACKAGE_FORMAT, "as_of_date": as_of, "generated_at_utc": generated,
                 "fund_count": len(records), "limitations": limitations, "funds": records, "automatic_execution_authorized": False}
    status_doc = {k: status[k] for k in ("policy_id", "generated_at_utc", "mode", "fund_count", "quality_summary", "freshness_summary")}
    enc = lambda doc: (json.dumps(doc, indent=1, default=lambda o: o.item()) + "\n").encode("utf-8")  # noqa: E731
    files = {"funds.json": (enc(funds_doc), len(records)), "groups.json": (enc({"groups": groups}), len(groups)),
             "latest_prices.csv": (U.latest_prices_csv(records).encode("utf-8"), len(records)),
             "research.json": (enc(research_doc), len(research_doc["timing"])), "market_data_status.json": (enc(status_doc), status["fund_count"])}
    manifest = U.write_package(args.output, files=files, validation=validation, commit=commit(), generated_at_utc=generated,
                               as_of=as_of, schema=schema, snapshot=files["market_data_status.json"][0])
    U.verify_package(args.output, schema)
    calls = {}
    for r in records:
        calls[r["ranking_call"]] = calls.get(r["ranking_call"], 0) + 1
    impl = sum(1 for r in records if r["implementation"]["call"] == "REDIRECT_NEW_MONEY")
    coverage_counts = {"projection_3y": sum(1 for r in records if r.get("projection_3y")),
                       "outlook_3y": sum(1 for r in records if r.get("outlook_3y")),
                       "neither": sorted(r["symbol"] for r in records if not r.get("projection_3y") and not r.get("outlook_3y")),
                       "loose_peer_reading": sum(1 for r in records if r.get("loose_peer_reading"))}
    print(json.dumps({"package_id": manifest["package_id"], "validation": validation, "funds": len(records), "groups": len(groups),
                      "ranking_calls": calls, "redirects": impl, "coverage": coverage_counts, "limitations": limitations}))
    return 0 if validation != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
