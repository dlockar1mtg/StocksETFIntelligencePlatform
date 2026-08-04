from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from foundation.universe.structural_triage import load_policy

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_2a_structural_triage_certification.json"
MINIMUM_TESTS = 223


def run_tests() -> tuple[int, str]:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(ROOT / "tests"),
        "-t",
        str(ROOT),
        "-p",
        "test_*.py",
        "-v",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(output)
    marker = "Ran "
    tests_run = 0
    for line in output.splitlines():
        if line.startswith(marker) and " tests in " in line:
            tests_run = int(line.split()[1])
    if tests_run < MINIMUM_TESTS:
        raise RuntimeError(f"Regression floor weakened: {tests_run} < {MINIMUM_TESTS}")
    return tests_run, output


def main() -> int:
    critical_failures: list[str] = []
    tests_run = 0
    try:
        policy = load_policy()
        registry = json.loads((ROOT / "config" / "contracts" / "contract_registry.json").read_text(encoding="utf-8"))
        schema_path = ROOT / "contracts" / "native" / "etf_structural_triage_record.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        registrations = [
            item for item in registry["contracts"]
            if item["contract_id"] == "native.etf_structural_triage_record"
        ]
        if len(registrations) != 1:
            raise RuntimeError("ETF structural triage contract must be registered exactly once")
        if registrations[0]["schema"] != "contracts/native/etf_structural_triage_record.schema.json":
            raise RuntimeError("ETF structural triage schema path drifted")
        if schema.get("additionalProperties") is not False:
            raise RuntimeError("ETF structural triage contract must fail closed on unknown fields")
        tests_run, _ = run_tests()
    except Exception as exc:  # certification must capture and fail closed
        critical_failures.append(str(exc))
        policy = None

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "2A",
        "certification_type": "BUILD_AND_CONTRACT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "selection_result": {
            "target_universe_size": None,
            "selection_principle": "EVIDENCE_DETERMINES_SIZE",
            "full_discovery_universe_preserved": True,
            "destructive_deletion_allowed": False,
        },
        "authorized": {
            "structural_triage_development": status == "PASS",
            "metadata_collection_development": status == "PASS",
            "market_screen_development": status == "PASS",
        },
        "unauthorized": {
            "production_data_certification": True,
            "production_analytics": True,
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
    print(f"Phase 2A structural triage certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    if critical_failures:
        for failure in critical_failures:
            print(f"CRITICAL: {failure}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
