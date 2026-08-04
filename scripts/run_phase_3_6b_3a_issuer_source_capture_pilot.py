from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from foundation.market.issuer_source_capture_pilot import (
    capture_record,
    failure_record,
    fetch_source,
    write_raw_content,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--raw-directory", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))["records"]
    manifest_records = {record["security_id"]: record for record in manifest["records"]}

    pilot_records = []
    for security_id, entry in registry.items():
        if security_id not in manifest_records:
            raise ValueError(f"PILOT_IDENTITY_NOT_IN_MANIFEST:{security_id}")
        try:
            content = fetch_source(entry)
            write_raw_content(Path(args.raw_directory), entry["symbol"], content)
            record = capture_record(security_id, entry, policy, content)
        except Exception as exc:
            record = failure_record(security_id, entry, exc)
        pilot_records.append(record)
        manifest_records[security_id] = {**manifest_records[security_id], **record}

    updated_records = [manifest_records[record["security_id"]] for record in manifest["records"]]
    counts = Counter(record["acquisition_state"] for record in updated_records)
    output = {
        **{key: value for key, value in manifest.items() if key != "records"},
        "phase": "3.6b.3a",
        "records": updated_records,
        "acquisition_state_counts": dict(sorted(counts.items())),
        "authority_captured_count": counts.get("AUTHORITY_CAPTURED", 0),
        "remaining_count": len(updated_records) - counts.get("AUTHORITY_CAPTURED", 0),
        "manifest_complete": counts.get("AUTHORITY_CAPTURED", 0) == len(updated_records),
        "next_required_step": "PILOT_EVIDENCE_NORMALIZATION_REVIEW",
        "pilot_records": pilot_records,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {key: value for key, value in output.items() if key not in {"records", "pilot_records"}}
    summary["pilot_state_counts"] = dict(Counter(record["acquisition_state"] for record in pilot_records))
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
