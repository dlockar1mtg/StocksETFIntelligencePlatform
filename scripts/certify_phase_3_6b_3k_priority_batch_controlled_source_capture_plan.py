from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPORT_PATH = Path(
    "artifacts/certification/phase_3_6b_3k_priority_batch_controlled_source_capture_plan_certification.json"
)
MINIMUM_TESTS = 582


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
    combined = result.stdout + "\n" + result.stderr

    tests_run = 0
    for line in combined.splitlines():
        stripped = line.strip()
        if stripped.startswith("Ran ") and " tests" in stripped:
            try:
                tests_run = int(stripped.split()[1])
            except (IndexError, ValueError):
                pass

    policy = json.loads(
        Path("config/market/priority_batch_controlled_source_capture_plan_policy.json").read_text(
            encoding="utf-8"
        )
    )
    authority = policy["authority"]
    critical_failures: list[str] = []
    if result.returncode != 0:
        critical_failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("REGRESSION_FLOOR_NOT_MET")
    if authority["controlled_priority_batch_capture_plan"] is not True:
        critical_failures.append("CAPTURE_PLAN_NOT_AUTHORIZED")
    if authority["controlled_priority_batch_capture_plan_certification"] is not True:
        critical_failures.append("CAPTURE_PLAN_CERTIFICATION_NOT_AUTHORIZED")
    for blocked in (
        "priority_batch_source_capture",
        "authoritative_source_capture",
        "taxonomy_evidence_normalization",
        "production_taxonomy_classification",
        "relative_return_calculation",
        "forecasting",
        "ranking",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    ):
        if authority[blocked] is not False:
            critical_failures.append(f"PREMATURE_AUTHORITY:{blocked}")

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "3.6b.3k",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "controlled_priority_batch_capture_plan_authorized": authority[
                "controlled_priority_batch_capture_plan"
            ],
            "controlled_priority_batch_capture_plan_certification_authorized": authority[
                "controlled_priority_batch_capture_plan_certification"
            ],
            "priority_batch_source_capture_authorized": authority[
                "priority_batch_source_capture"
            ],
            "taxonomy_evidence_normalization_authorized": authority[
                "taxonomy_evidence_normalization"
            ],
            "production_taxonomy_classification_authorized": authority[
                "production_taxonomy_classification"
            ],
            "relative_return_calculation_authorized": authority[
                "relative_return_calculation"
            ],
        },
        "critical_failures": critical_failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"Phase 3.6b.3k priority batch controlled source capture plan certification: {status}"
    )
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH.resolve()}")
    if result.returncode != 0:
        print(combined)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
