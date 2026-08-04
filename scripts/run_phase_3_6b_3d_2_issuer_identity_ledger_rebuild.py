from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.issuer_identity_ledger_rebuild import build_issuer_identity_ledger, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-plan", required=True)
    parser.add_argument("--sec-identities", required=True)
    parser.add_argument("--registrant-registry", required=True)
    parser.add_argument("--pilot-taxonomy", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    result = build_issuer_identity_ledger(
        load(args.batch_plan),
        load(args.sec_identities),
        load(args.registrant_registry),
        load(args.pilot_taxonomy),
        load(args.policy),
    )
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
