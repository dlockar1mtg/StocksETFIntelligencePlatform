from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MINIMUM_TESTS_REQUIRED = 612
REPORT_PATH = Path(
    "artifacts/certification/phase_3_6b_3n_priority_batch_capture_ledger_review_certification.json"
)


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-t",
        ".",
        "-p",
        "test_*.py",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    combined = f"{result.stdout}\n{result.stderr}"
    tests_run = 0
    for line in combined.splitlines():
        stripped = line.strip()
        if stripped.startswith("Ran ") and " tests" in stripped:
            try:
                tests_run = int(stripped.split()[1])
            except (IndexError, ValueError):
                pass

    failures: list[str] = []
    if result.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS_REQUIRED:
        failures.append("REGRESSION_TEST_FLOOR_NOT_MET")

    report = {
        "phase": "3.6b.3n",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS_REQUIRED,
        "certification_result": {
            "capture_ledger_review_authorized": True,
            "capture_ledger_certification_authorized": False,
            "taxonomy_evidence_normalization_authorized": False,
            "production_taxonomy_classification_authorized": False,
            "relative_return_calculation_authorized": False,
            "automatic_execution_authorized": False,
        },
        "critical_failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        "Phase 3.6b.3n priority batch capture ledger review certification: "
        f"{report['status']}"
    )
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH.resolve()}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
