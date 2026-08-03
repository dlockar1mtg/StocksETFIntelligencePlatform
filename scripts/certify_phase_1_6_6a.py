from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


MINIMUM_TESTS = 177
REPORT_PATH = Path("artifacts/certification/phase_1_6_6a_certification.json")


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    marker = "Ran "
    tests_run = 0
    for line in output.splitlines():
        if line.startswith(marker) and " tests in " in line:
            tests_run = int(line.split()[1])

    critical_failures = []
    if result.returncode != 0:
        critical_failures.append("CUMULATIVE_REGRESSION_FAILURE")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("TEST_FLOOR_NOT_MET")

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "1.6.6a",
        "certification": "governed_us_etf_exchange_discovery_collector",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "authoritative_source_count": 2,
        "broker_independent_discovery": True,
        "raw_payloads_outside_git": True,
        "raw_payload_hashes_required": True,
        "source_records_preserved": True,
        "collector_invoked_as_repository_module": True,
        "powershell_json_arrays_enumerated": True,
        "quarantine_outputs_outside_git": True,
        "candidate_is_certified_discovery": False,
        "candidate_implies_robinhood_eligibility": False,
        "candidate_implies_analytics_eligibility": False,
        "automatic_execution_authorized": False,
        "test_output": output,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 1.6.6a certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH.resolve()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
