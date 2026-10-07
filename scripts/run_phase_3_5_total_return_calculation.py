from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from foundation.market.total_return_calculation import calculate_universe

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "market" / "total_return_calculation_policy.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certification", required=True)
    parser.add_argument("--certification-summary", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    certification_path = Path(args.certification)
    certification_summary_path = Path(args.certification_summary)
    raw_root = Path(args.raw_root)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    prior_summary = json.loads(certification_summary_path.read_text(encoding="utf-8"))
    if int(certification.get("record_count") or 0) != int(policy["required_record_count"]):
        raise SystemExit("PHASE_3_4_RECORD_COUNT_MISMATCH")
    if certification.get("reason_counts"):
        raise SystemExit("PHASE_3_4_HAS_CERTIFICATION_REASONS")
    if prior_summary.get("return_calculation_authorized") is not False:
        raise SystemExit("PHASE_3_4_AUTHORITY_STATE_DRIFT")

    result = calculate_universe(certification, raw_root=raw_root, policy=policy)
    result["operating_date"] = args.operating_date
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "phase": "3.5",
        "operating_date": args.operating_date,
        "record_count": result["record_count"],
        "horizon_calculated_counts": result["horizon_calculated_counts"],
        "return_basis": result["return_basis"],
        "phase_3_4_certification_sha256": _sha256(certification_path),
        "phase_3_4_summary_sha256": _sha256(certification_summary_path),
        "total_return_output_sha256": _sha256(output_path),
        "return_calculation_authorized": True,
        "risk_analytics_authorized": False,
        "benchmark_comparison_authorized": False,
        "forecasting_authorized": False,
        "ranking_authorized": False,
        "recommendations_authorized": False,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
