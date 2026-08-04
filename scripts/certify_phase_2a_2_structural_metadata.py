from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.infrastructure.structural_metadata import load_policy

REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_2a_2_structural_metadata_certification.json"
MINIMUM_TESTS = 240


def run_tests() -> int:
    command = [
        sys.executable, "-m", "unittest", "discover",
        "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(output)
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests in " in line:
            tests_run = int(line.split()[1])
    if tests_run < MINIMUM_TESTS:
        raise RuntimeError(f"Regression floor weakened: {tests_run} < {MINIMUM_TESTS}")
    return tests_run


def main() -> int:
    failures: list[str] = []
    tests_run = 0
    policy = None
    try:
        policy = load_policy()
        registry = json.loads((ROOT / "config" / "contracts" / "contract_registry.json").read_text(encoding="utf-8"))
        schema_path = ROOT / "contracts" / "native" / "etf_structural_metadata_record.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        registrations = [item for item in registry["contracts"] if item["contract_id"] == "native.etf_structural_metadata_record"]
        if len(registrations) != 1:
            raise RuntimeError("Structural metadata contract must be registered exactly once")
        if registrations[0]["schema"] != "contracts/native/etf_structural_metadata_record.schema.json":
            raise RuntimeError("Structural metadata schema path drifted")
        if schema.get("additionalProperties") is not False:
            raise RuntimeError("Structural metadata contract must fail closed")
        if not (ROOT / "scripts" / "build_structural_metadata_snapshot.py").exists():
            raise RuntimeError("Structural metadata snapshot builder is missing")
        tests_run = run_tests()
    except Exception as exc:
        failures.append(str(exc))

    status = "PASS" if not failures else "FAIL"
    report = {
        "phase": "2A.2",
        "certification_type": "BUILD_CONTRACT_AND_RECONCILIATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "selection_result": {
            "selection_principle": "EVIDENCE_DETERMINES_SIZE",
            "target_universe_size": None,
            "full_discovery_universe_preserved": True,
            "raw_evidence_immutable": True,
        },
        "authorized": {
            "official_metadata_collection_development": status == "PASS",
            "metadata_reconciliation_development": status == "PASS",
            "triage_snapshot_development": status == "PASS",
        },
        "unauthorized": {
            "production_data_certification": True,
            "analytics": True,
            "forecasting": True,
            "ranking": True,
            "recommendations": True,
            "portfolio_allocation": True,
            "uip_export": True,
            "automatic_execution": True,
            "direct_uip_database_writes": True,
        },
        "policy_version": policy["policy_version"] if policy else None,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 2A.2 structural metadata certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    for failure in failures:
        print(f"CRITICAL: {failure}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
