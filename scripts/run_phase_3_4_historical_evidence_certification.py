from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from foundation.market.historical_evidence_certification import certify_universe

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "market" / "historical_evidence_certification_policy.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--attestation", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    attestation_path = Path(args.attestation)
    raw_root = Path(args.raw_root)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    records = list(checkpoint.get("records") or [])

    if attestation.get("completion_status") != "COMPLETE":
        raise SystemExit("Historical collection attestation is not COMPLETE")
    if int(attestation.get("completed_records") or 0) != int(policy["required_record_count"]):
        raise SystemExit("Historical collection attestation count drifted")
    if attestation.get("checkpoint_sha256") != _sha256(checkpoint_path):
        raise SystemExit("Historical checkpoint hash does not match completion attestation")

    result = certify_universe(
        records,
        raw_root=raw_root,
        operating_date=args.operating_date,
        policy=policy,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "phase": "3.4",
        "operating_date": args.operating_date,
        "record_count": result["record_count"],
        "state_counts": result["state_counts"],
        "reason_counts": result["reason_counts"],
        "horizon_eligible_counts": result["horizon_eligible_counts"],
        "all_input_records_preserved": result["all_input_records_preserved"],
        "checkpoint_sha256": _sha256(checkpoint_path),
        "completion_attestation_sha256": _sha256(attestation_path),
        "certification_output_sha256": _sha256(output_path),
        "return_calculation_authorized": False,
        "risk_analytics_authorized": False,
        "forecasting_authorized": False,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
