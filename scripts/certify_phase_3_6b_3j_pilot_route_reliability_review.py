from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6b_3j_pilot_route_reliability_review_certification.json"
MINIMUM_TESTS = 572


def main() -> int:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    policy = json.loads((ROOT / "config/market/pilot_route_reliability_review_policy.json").read_text(encoding="utf-8"))
    critical_failures: list[str] = []
    if result.returncode != 0:
        critical_failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("TEST_FLOOR_NOT_MET")
    if policy["authority"]["priority_batch_source_capture"] is not False:
        critical_failures.append("PREMATURE_BATCH_CAPTURE_AUTHORITY")
    if policy["authority"]["production_taxonomy_classification"] is not False:
        critical_failures.append("PREMATURE_TAXONOMY_AUTHORITY")

    report = {
        "phase": "3.6b.3j",
        "status": "PASS" if not critical_failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "certification_result": {
            "pilot_route_reliability_review_authorized": policy["authority"]["pilot_route_reliability_review"],
            "pilot_route_reliability_certification_authorized": policy["authority"]["pilot_route_reliability_certification"],
            "controlled_priority_batch_capture_plan_authorized": policy["authority"]["controlled_priority_batch_capture_plan"],
            "priority_batch_source_capture_authorized": policy["authority"]["priority_batch_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Phase 3.6b.3j pilot route reliability review certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
