from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.full_universe_benchmark_assignment import build_full_universe_assignment, write_outputs

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--returns", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    args = parser.parse_args()

    policy = load(ROOT / "config/market/full_universe_benchmark_assignment_policy.json")
    registry_policy = load(ROOT / "config/market/benchmark_assignment_registry_policy.json")
    rules = load(ROOT / "config/market/benchmark_assignment_rules.json")
    result = build_full_universe_assignment(
        load(args.taxonomy), load(args.returns), policy, registry_policy, rules
    )
    write_outputs(result, args.output, args.summary, args.candidates)
    print(json.dumps({
        "phase": result["phase"],
        "record_count": result["record_count"],
        "assignment_state_counts": result["assignment_state_counts"],
        "active_analytical_candidate_count": result["active_analytical_candidate_count"],
        "excluded_preserved_count": result["excluded_preserved_count"],
        "benchmark_qualified_universe_publication_authorized": result["authority"]["benchmark_qualified_universe_publication"],
        "relative_return_calculation_authorized": result["authority"]["relative_return_calculation"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
