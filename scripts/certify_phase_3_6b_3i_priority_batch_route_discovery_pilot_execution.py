from __future__ import annotations

import json
import subprocess
from pathlib import Path


def main() -> None:
    result = subprocess.run(
        ["python", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        capture_output=True,
        text=True,
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = max(tests_run, int(line.split()[1]))
    report = {
        "phase": "3.6b.3i",
        "status": "PASS" if result.returncode == 0 and tests_run >= 562 else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": 562,
        "certification_result": {
            "route_discovery_pilot_execution_authorized": True,
            "route_discovery_pilot_result_analysis_authorized": True,
            "priority_batch_source_capture_authorized": False,
            "authoritative_source_capture_authorized": False,
            "production_taxonomy_classification_authorized": False,
            "relative_return_calculation_authorized": False,
        },
        "critical_failures": [] if result.returncode == 0 and tests_run >= 562 else ["REGRESSION_OR_TEST_FLOOR_FAILURE"],
    }
    path = Path("artifacts/certification/phase_3_6b_3i_priority_batch_route_discovery_pilot_execution_certification.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Phase 3.6b.3i priority batch route discovery pilot execution certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {path.resolve()}")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
