from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from foundation.market.full_historical_collection import build_completion_attestation, load_json, validate_candidate_universe, validate_pilot

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "market" / "full_historical_collection_authorization_policy.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-universe", required=True)
    parser.add_argument("--pilot-checkpoint", required=True)
    parser.add_argument("--operating-date", required=True)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    policy = load_json(POLICY_PATH)
    candidate_path = Path(args.candidate_universe)
    pilot_path = Path(args.pilot_checkpoint)
    validate_candidate_universe(load_json(candidate_path), policy)
    validate_pilot(load_json(pilot_path), policy)

    command = [
        sys.executable, "-m", "scripts.run_phase_3_2_historical_market_data_collection",
        "--candidate-universe", str(candidate_path),
        "--operating-date", args.operating_date,
    ]
    if args.retry_failed:
        command.append("--retry-failed")
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        return completed.returncode

    output_dir = ROOT / "data" / "staged" / "historical_market_data" / args.operating_date
    checkpoint_path = output_dir / "historical_collection_checkpoint.json"
    summary_path = output_dir / "historical_collection_summary.json"
    attestation_path = output_dir / "historical_collection_attestation.json"
    attestation = build_completion_attestation(
        candidate_path=candidate_path,
        checkpoint_path=checkpoint_path,
        summary_path=summary_path,
        policy=policy,
    )
    attestation_path.write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(attestation, indent=2, sort_keys=True))
    return 0 if attestation["completion_status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
