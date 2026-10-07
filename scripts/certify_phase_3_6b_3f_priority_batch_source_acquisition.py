from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


MINIMUM_TESTS = 532
REPORT = Path("artifacts/certification/phase_3_6b_3f_priority_batch_source_acquisition_certification.json")
POLICY = Path("config/market/priority_batch_source_acquisition_policy.json")


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    process = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"], capture_output=True, text=True)
    combined = process.stdout + process.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    failures: list[str] = []
    if process.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("REGRESSION_TEST_FLOOR_NOT_MET")
    if policy["selected_priority_rank"] != 1 or policy["selected_security_count"] != 347:
        failures.append("PRIORITY_BATCH_CONTRACT_DRIFT")
    if policy["authority"]["priority_batch_manifest_build"] is not True:
        failures.append("MANIFEST_BUILD_NOT_AUTHORIZED")
    for blocked in ("priority_batch_source_capture", "authoritative_source_capture", "production_taxonomy_classification", "relative_return_calculation", "forecasting", "ranking"):
        if policy["authority"][blocked] is not False:
            failures.append(f"PREMATURE_AUTHORITY_{blocked.upper()}")
    report = {
        "phase": "3.6b.3f",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "priority_batch_manifest_build_authorized": policy["authority"]["priority_batch_manifest_build"],
            "priority_batch_source_capture_authorized": policy["authority"]["priority_batch_source_capture"],
            "authoritative_source_capture_authorized": policy["authority"]["authoritative_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
        "critical_failures": failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3f priority batch source acquisition control certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT.resolve()}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
