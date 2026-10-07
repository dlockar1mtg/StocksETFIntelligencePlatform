from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.issuer_batch_expansion import build_issuer_batch_plan, write_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 3.6b.3c issuer batch plan.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--pilot-taxonomy", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    pilot_taxonomy = json.loads(args.pilot_taxonomy.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8"))

    result = build_issuer_batch_plan(manifest, pilot_taxonomy, policy)
    write_outputs(result, args.output, args.summary)
    print(json.dumps({key: value for key, value in result.items() if key not in {"records", "batches"}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
