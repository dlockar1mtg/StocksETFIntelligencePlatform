from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.infrastructure.structural_metadata import reconcile_records, summarize_coverage


def read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            records.append(value)
    return records


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build governed ETF structural metadata snapshot")
    parser.add_argument("--input", action="append", required=True, help="Normalized source JSONL; repeat for multiple sources")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operating-date", required=True)
    args = parser.parse_args()

    input_paths = [Path(value).resolve() for value in args.input]
    for path in input_paths:
        if not path.exists():
            raise FileNotFoundError(path)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "etf_structural_metadata_snapshot.jsonl"
    coverage_path = output_dir / "etf_structural_metadata_coverage.json"
    manifest_path = output_dir / "etf_structural_metadata_manifest.json"

    source_records = [record for path in input_paths for record in read_jsonl(path)]
    reconciled = reconcile_records(source_records)
    coverage = summarize_coverage(reconciled)
    write_jsonl(snapshot_path, reconciled)
    coverage_path.write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "snapshot_id": f"etf-structural-metadata-{args.operating_date}",
        "operating_date": args.operating_date,
        "operating_timezone": "America/Chicago",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "selection_principle": "EVIDENCE_DETERMINES_SIZE",
        "target_universe_size": None,
        "source_files": [
            {"path": str(path), "sha256": sha256_file(path), "row_count": len(read_jsonl(path))}
            for path in input_paths
        ],
        "outputs": [
            {"path": snapshot_path.name, "sha256": sha256_file(snapshot_path), "row_count": len(reconciled)},
            {"path": coverage_path.name, "sha256": sha256_file(coverage_path), "row_count": 1},
        ],
        "authority": {
            "production_data_certified": False,
            "analytics_authorized": False,
            "recommendations_authorized": False,
            "uip_export_authorized": False,
            "automatic_execution_authorized": False,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Source records: {len(source_records)}")
    print(f"Reconciled records: {len(reconciled)}")
    print(f"Snapshot: {snapshot_path}")
    print(f"Coverage: {coverage_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
