from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.authoritative_etf_taxonomy_normalization import (
    build_taxonomy_snapshot,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=ROOT / "config/market/authoritative_etf_taxonomy_registry.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/market/authoritative_etf_taxonomy_normalization_policy.json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    result = build_taxonomy_snapshot(evidence, registry, policy)
    write_outputs(result, args.output, args.summary)
    print(json.dumps({
        "phase": result["phase"],
        "record_count": result["record_count"],
        "classification_state_counts": result["classification_state_counts"],
        "taxonomy_snapshot_certified": result["taxonomy_snapshot_certified"],
        "next_required_step": result["next_required_step"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
