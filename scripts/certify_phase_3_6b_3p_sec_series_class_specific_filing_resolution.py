from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MINIMUM_TESTS = 635
REPORT = Path("artifacts/certification/phase_3_6b_3p_sec_series_class_specific_filing_resolution_certification.json")


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    combined = result.stdout + "\n" + result.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    critical_failures = []
    if result.returncode != 0:
        critical_failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("REGRESSION_FLOOR_NOT_MET")
    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "3.6b.3p",
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "series_class_resolution_pilot_authorized": status == "PASS",
            "series_class_route_reliability_review_authorized": status == "PASS",
            "series_class_route_reliability_certification_authorized": False,
            "full_priority_batch_recapture_authorized": False,
            "taxonomy_evidence_normalization_authorized": False,
            "production_taxonomy_classification_authorized": False,
            "automatic_execution_authorized": False,
        },
        "critical_failures": critical_failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3p SEC series/class-specific filing resolution certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT.resolve()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
