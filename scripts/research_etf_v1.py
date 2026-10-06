"""Run the ETF v1 research on the curated series and write the evidence file.

Usage: python scripts/research_etf_v1.py [--data data/curated/etf] [--output data/curated/etf/research/etf_v1_research.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market_data import analytics as A  # noqa: E402
from foundation.market_data import research as R  # noqa: E402

MODEL = ROOT / "config" / "market" / "etf_v1_model.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "curated" / "etf")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    config = json.loads(MODEL.read_text(encoding="utf-8"))
    prices = args.data / "prices"
    series = {p.stem: A.load_series(p) for p in sorted(prices.glob("*.csv"))}
    cash = series[config["cash_proxy"]]
    research_set = sorted(set(config["research_proxies"].values()))
    tested = {t: series[t] for t in research_set if t in series}
    report = {
        "model_id": config["model_id"], "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_through": {t: s.days[-1] for t, s in series.items()},
        "history_from": {t: s.days[0] for t, s in series.items()},
        "signal_study": R.signal_study(tested),
        "timing_rules": R.walk_forward(tested, cash, config),
        "cross_sectional_momentum": {
            "since_2000": {f"{h}m": R.cross_sectional_momentum(series, ["SPY", "QQQ", "DIA", "IWM"], h) for h in (12, 36)},
            "since_2011": {f"{h}m": R.cross_sectional_momentum(series, ["SPY", "QQQ", "DIA", "IWM", "SCHD"], h) for h in (12, 36)},
        },
        "gate": config["gate"],
    }
    report["any_rule_passes"] = any(r["passes_gate"] for r in report["timing_rules"].values())
    out = args.output or (args.data / "research" / "etf_v1_research.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for family, r in report["timing_rules"].items():
        print(f"{family:16} starts {r['out_of_sample_starts']:4} beat {r['share_beating']} median {r['median_edge']} "
              f"worst {r['worst_edge']} params {r['parameters_chosen']} pass {r['passes_gate']}")
    for key, v in report["signal_study"]["pooled"].items():
        print(f"pooled {key:20} rho {v['rank_correlation']} n {v['samples']}")
    print(json.dumps(report["cross_sectional_momentum"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
