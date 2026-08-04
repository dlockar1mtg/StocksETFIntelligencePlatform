from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.evidence_backed_issuer_identity import build_issuer_identity_ledger, write_outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-plan", type=Path, required=True)
    parser.add_argument("--sec-identities", type=Path, required=True)
    parser.add_argument("--pilot-taxonomy", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    result = build_issuer_identity_ledger(
        json.loads(args.batch_plan.read_text(encoding="utf-8")),
        json.loads(args.sec_identities.read_text(encoding="utf-8")),
        json.loads(args.pilot_taxonomy.read_text(encoding="utf-8")),
        json.loads(args.policy.read_text(encoding="utf-8")),
    )
    write_outputs(result, args.output, args.summary)
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
