from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.universe.structural_identity_resolution import resolve_identities


def _load_records(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = document.get("records", document if isinstance(document, list) else None)
    if not isinstance(records, list):
        raise RuntimeError(f"Input must be a list or contain records: {path}")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--sec-reconciliation", required=True)
    parser.add_argument("--operating-date", required=True)
    args = parser.parse_args()

    universe_path = Path(args.universe)
    sec_path = Path(args.sec_reconciliation)
    universe = _load_records(universe_path)
    sec_reconciliation = json.loads(sec_path.read_text(encoding="utf-8"))
    result = resolve_identities(sec_reconciliation, universe)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result.update({
        "phase": "2A.4",
        "operating_date": args.operating_date,
        "generated_at_utc": generated_at,
        "universe_input": str(universe_path),
        "sec_reconciliation_input": str(sec_path),
    })

    output_dir = ROOT / "data" / "staged" / "structural_identity" / args.operating_date
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "sec_matched_structural_metadata.json": {
            "phase": "2A.4", "operating_date": args.operating_date,
            "generated_at_utc": generated_at, "records": result["matched_records"],
        },
        "sec_unmatched_attribution.json": {
            "phase": "2A.4", "operating_date": args.operating_date,
            "generated_at_utc": generated_at, "records": result["unmatched_records"],
        },
        "structural_identity_coverage_summary.json": {
            key: result[key] for key in (
                "phase", "operating_date", "generated_at_utc", "total_records",
                "sec_identity_confirmed", "unmatched_or_conflicted", "resolution_state_counts",
                "unmatched_reason_counts", "selection_principle", "target_universe_size",
                "full_discovery_universe_preserved", "destructive_deletion_allowed",
            )
        },
        "phase_2a_4_identity_resolution_snapshot.json": result,
    }
    for name, payload in outputs.items():
        (output_dir / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "total_records": result["total_records"],
        "sec_identity_confirmed": result["sec_identity_confirmed"],
        "unmatched_or_conflicted": result["unmatched_or_conflicted"],
        "resolution_state_counts": result["resolution_state_counts"],
        "unmatched_reason_counts": result["unmatched_reason_counts"],
    }, indent=2))
    print(f"Output directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
