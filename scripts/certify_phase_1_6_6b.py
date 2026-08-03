from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MINIMUM_TESTS = 186
REPORT_PATH = Path("artifacts/certification/phase_1_6_6b_certification.json")


def main() -> int:
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"], capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests in " in line:
            tests_run = int(line.split()[1])
    failures = []
    if result.returncode != 0:
        failures.append("CUMULATIVE_REGRESSION_FAILURE")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    status = "PASS" if not failures else "FAIL"
    report = {
        "phase": "1.6.6b",
        "certification": "governed_robinhood_availability_collector",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "resumable": True,
        "rate_limited": True,
        "affirmative_buy_evidence_required": True,
        "unknown_or_failed_lookup_is_eligible": False,
        "position_closing_only_is_eligible": False,
        "capabilities_are_independent": True,
        "raw_response_hashes_required": True,
        "analytics_eligibility_implied": False,
        "automatic_execution_authorized": False,
        "test_output": output,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 1.6.6b certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH.resolve()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
