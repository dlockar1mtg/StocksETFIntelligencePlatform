from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    minimum = 542
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"]
    completed = subprocess.run(command, capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads(Path("config/market/priority_batch_source_route_resolution_policy.json").read_text(encoding="utf-8"))
    failures = []
    if completed.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < minimum:
        failures.append("REGRESSION_FLOOR_NOT_MET")
    if policy["authority"]["priority_batch_source_route_resolution"] is not True:
        failures.append("ROUTE_RESOLUTION_NOT_AUTHORIZED")
    for key in ("priority_batch_source_capture", "production_taxonomy_classification", "relative_return_calculation"):
        if policy["authority"][key] is not False:
            failures.append(f"PREMATURE_AUTHORITY_{key.upper()}")
    report = {
        "phase": "3.6b.3g",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": minimum,
        "critical_failures": failures,
        "certification_result": {
            "priority_batch_source_route_resolution_authorized": policy["authority"]["priority_batch_source_route_resolution"],
            "priority_batch_route_coverage_analysis_authorized": policy["authority"]["priority_batch_route_coverage_analysis"],
            "priority_batch_source_capture_authorized": policy["authority"]["priority_batch_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
    }
    path = Path("artifacts/certification/phase_3_6b_3g_priority_batch_source_route_resolution_certification.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3g priority batch source route resolution certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {path.resolve()}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
