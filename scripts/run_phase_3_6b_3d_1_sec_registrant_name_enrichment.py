from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.sec_registrant_name_enrichment import collect_registry, extract_required_ciks, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-plan", required=True)
    parser.add_argument("--sec-identities", required=True)
    parser.add_argument("--pilot-taxonomy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--raw-directory", required=True)
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()

    batch_plan = json.loads(Path(args.batch_plan).read_text(encoding="utf-8"))
    identities = json.loads(Path(args.sec_identities).read_text(encoding="utf-8"))
    pilot = json.loads(Path(args.pilot_taxonomy).read_text(encoding="utf-8"))

    allowed_ids = {record["security_id"] for record in batch_plan["records"]}
    if len(allowed_ids) != 3462:
        raise ValueError("PHASE_3_POPULATION_IDENTITY_MISMATCH")
    identity_records = [record for record in identities["records"] if record.get("security_id") in allowed_ids]
    filtered_identities = {"records": identity_records}
    pilot_ids = {record["security_id"] for record in pilot["records"]}
    ciks = extract_required_ciks(filtered_identities, pilot_ids)

    result = collect_registry(ciks, Path(args.raw_directory), args.user_agent)
    result["phase_3_security_count"] = len(allowed_ids)
    result["pilot_security_count"] = len(pilot_ids)
    write_outputs(result, Path(args.output), Path(args.summary))
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
