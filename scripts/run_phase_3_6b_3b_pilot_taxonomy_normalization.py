from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.pilot_taxonomy_normalization import fetch_source, normalize_pilot_record, summarize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--raw-directory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))["records"]
    records_by_id = {record["security_id"]: record for record in manifest["records"]}
    raw_directory = Path(args.raw_directory)

    results = []
    for security_id in policy["required_security_ids"]:
        manifest_record = records_by_id.get(security_id)
        if manifest_record is None:
            raise ValueError(f"PILOT_IDENTITY_NOT_IN_MANIFEST:{security_id}")
        entry = registry[security_id]
        content = None
        raw_path = raw_directory / f"{entry['symbol'].lower()}_issuer_source.bin"
        if raw_path.exists():
            content = raw_path.read_bytes()
        elif manifest_record.get("acquisition_state") != "AUTHORITY_CAPTURED":
            try:
                content = fetch_source(entry["source_url"])
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(content)
            except Exception:
                content = None
        results.append(normalize_pilot_record(manifest_record, entry, policy, content))

    summary = summarize(results, policy)
    output = Path(args.output)
    summary_path = Path(args.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({**summary, "records": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
