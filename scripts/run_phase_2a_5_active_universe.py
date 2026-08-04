from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.universe.active_structural_universe import promote_active_universe


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-snapshot", required=True)
    parser.add_argument("--operating-date", required=True)
    args = parser.parse_args()

    source = json.loads(Path(args.identity_snapshot).read_text(encoding="utf-8"))
    result = promote_active_universe(source)
    result["operating_date"] = args.operating_date
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    output = ROOT / "data" / "staged" / "active_universe" / args.operating_date
    write_json(output / "active_structural_universe.json", {"records": result["active_records"]})
    write_json(output / "deferred_research_only_universe.json", {"records": result["deferred_records"]})
    write_json(output / "active_structural_universe_summary.json", {key: value for key, value in result.items() if key not in {"active_records", "deferred_records"}})
    print(json.dumps({key: result[key] for key in ("total_discovery_records", "active_structural_records", "deferred_research_only_records")}, indent=2))
    print(f"Output directory: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
