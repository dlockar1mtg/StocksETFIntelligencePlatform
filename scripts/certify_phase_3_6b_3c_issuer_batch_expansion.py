from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/market/issuer_batch_expansion_policy.json"
REPORT_PATH = ROOT / "artifacts/certification/phase_3_6b_3c_issuer_batch_expansion_certification.json"
MINIMUM_TESTS = 482


def main() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = completed.stdout + completed.stderr
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    critical_failures = []
    if completed.returncode != 0:
        critical_failures.append("CUMULATIVE_TEST_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_full_population") != 3462 or policy.get("remaining_population") != 3459:
        critical_failures.append("POPULATION_CONTRACT_DRIFT")
    if policy.get("authority", {}).get("issuer_batch_planning") is not True:
        critical_failures.append("BATCH_PLANNING_NOT_AUTHORIZED")
    for key in (
        "authoritative_source_capture",
        "production_taxonomy_classification",
        "relative_return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
    ):
        if policy.get("authority", {}).get(key) is not False:
            critical_failures.append(f"PREMATURE_AUTHORITY:{key}")

    report = {
        "phase": "3.6b.3c",
        "status": "PASS" if not critical_failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "certification_result": {
            "required_full_population": policy.get("required_full_population"),
            "remaining_population": policy.get("remaining_population"),
            "issuer_batch_planning_authorized": policy["authority"]["issuer_batch_planning"],
            "coverage_prioritization_authorized": policy["authority"]["coverage_prioritization"],
            "authoritative_source_capture_authorized": policy["authority"]["authoritative_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3c issuer batch expansion certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    if critical_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
