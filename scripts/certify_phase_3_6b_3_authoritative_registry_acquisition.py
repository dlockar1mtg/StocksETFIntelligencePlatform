from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6b_3_authoritative_registry_acquisition_certification.json"
POLICY = ROOT / "config/market/authoritative_etf_taxonomy_registry_acquisition_policy.json"
MINIMUM_TESTS = 452


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_record_count") != 3462:
        failures.append("REQUIRED_RECORD_COUNT_DRIFT")
    if policy.get("authority", {}).get("authoritative_source_capture") is not False:
        failures.append("SOURCE_CAPTURE_PREMATURELY_AUTHORIZED")
    for key in (
        "production_taxonomy_classification",
        "production_taxonomy_certification",
        "relative_return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    ):
        if policy.get("authority", {}).get(key) is not False:
            failures.append(f"{key.upper()}_PREMATURELY_AUTHORIZED")

    report = {
        "phase": "3.6b.3",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "required_records": policy["required_record_count"],
            "acquisition_states": policy["acquisition_states"],
            "authoritative_source_tiers": policy["authoritative_source_tiers"],
            "acquisition_planning_authorized": policy["authority"]["authoritative_registry_acquisition_planning"],
            "manifest_build_authorized": policy["authority"]["authoritative_evidence_manifest_build"],
            "source_capture_authorized": policy["authority"]["authoritative_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3 authoritative registry acquisition certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
