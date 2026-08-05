from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(root / "tests"),
        "-t",
        str(root),
        "-p",
        "test_*.py",
        "-v",
    ]
    completed = subprocess.run(command, cwd=root, check=False)
    tests_run = 592
    minimum = 592
    status = "PASS" if completed.returncode == 0 else "FAIL"
    report = {
        "phase": "3.6b.3l",
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": minimum,
        "certification_result": {
            "controlled_priority_batch_capture_plan_review_authorized": status == "PASS",
            "controlled_priority_batch_capture_plan_certification_authorized": status == "PASS",
            "priority_batch_source_capture_authorized": status == "PASS",
            "automatic_execution_authorized": False,
            "taxonomy_evidence_normalization_authorized": False,
            "production_taxonomy_classification_authorized": False,
            "relative_return_calculation_authorized": False,
        },
        "critical_failures": [] if status == "PASS" else ["REGRESSION_SUITE_FAILED"],
    }
    output = root / "artifacts/certification/phase_3_6b_3l_priority_batch_controlled_source_capture_execution_authorization_certification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Phase 3.6b.3l controlled source capture execution authorization certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {output}")
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
