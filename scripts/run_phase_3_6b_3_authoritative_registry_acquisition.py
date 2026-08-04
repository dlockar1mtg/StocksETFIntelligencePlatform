from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_registry_acquisition import (
    build_acquisition_manifest,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy-gaps", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--existing-manifest")
    args = parser.parse_args()

    gaps = json.loads(Path(args.taxonomy_gaps).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    existing = None
    if args.existing_manifest and Path(args.existing_manifest).exists():
        existing = json.loads(Path(args.existing_manifest).read_text(encoding="utf-8"))

    result = build_acquisition_manifest(gaps, policy, existing)
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({
        "record_count": result["record_count"],
        "acquisition_state_counts": result["acquisition_state_counts"],
        "authority_captured_count": result["authority_captured_count"],
        "remaining_count": result["remaining_count"],
        "manifest_complete": result["manifest_complete"],
        "next_required_step": result["next_required_step"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
