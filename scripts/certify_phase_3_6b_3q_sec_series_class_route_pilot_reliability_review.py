from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MINIMUM_TESTS = 646
REPORT = Path("artifacts/certification/phase_3_6b_3q_sec_series_class_route_pilot_reliability_review_certification.json")


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
        "phase": "3.6b.3q",
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "reliability_review_execution_authorized": status == "PASS",
            "reliability_review_certification_authorized": status == "PASS",
            "targeted_aaxj_remediation_authorized": status == "PASS",
            "series_class_route_reliability_certified": False,
            "expanded_pilot_authorized": False,
            "route_correction_authorized": False,
            "full_priority_batch_recapture_authorized": False,
            "taxonomy_evidence_normalization_authorized": False,
            "production_taxonomy_classification_authorized": False,
            "benchmark_publication_authorized": False,
            "relative_return_analytics_authorized": False,
            "forecasting_authorized": False,
            "ranking_authorized": False,
            "recommendations_authorized": False,
            "portfolio_allocation_authorized": False,
            "uip_export_authorized": False,
            "automatic_execution_authorized": False,
            "direct_uip_database_writes_authorized": False
        },
        "next_required_step": "RUN_GOVERNED_RELIABILITY_REVIEW_THEN_TARGETED_AAXJ_HISTORICAL_SEC_REMEDIATION",
        "critical_failures": critical_failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3q SEC series/class route pilot reliability review certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT.resolve()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
