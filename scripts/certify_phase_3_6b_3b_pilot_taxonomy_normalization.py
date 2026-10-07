from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6b_3b_pilot_taxonomy_normalization_certification.json"
MINIMUM_TESTS = 472


def main() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    failures = []
    if completed.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")

    policy = json.loads((ROOT / "config/market/pilot_taxonomy_normalization_policy.json").read_text())
    result = {
        "phase": "3.6b.3b",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "pilot_record_count": policy["required_record_count"],
            "pilot_source_remediation_authorized": policy["authority"]["pilot_source_remediation"],
            "pilot_taxonomy_classification_authorized": policy["authority"]["pilot_taxonomy_classification"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"]
        }
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3b pilot taxonomy normalization certification: {result['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
