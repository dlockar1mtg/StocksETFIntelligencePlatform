from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.phase_2b_foundation_certification import certify_and_publish


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eligibility", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    result = certify_and_publish(Path(args.eligibility), Path(args.summary), Path(args.output_dir))
    print(json.dumps(result["attestation"], indent=2, sort_keys=True))
    print(f"Candidate universe: {result['candidate_path']}")
    print(f"Attestation: {result['attestation_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
