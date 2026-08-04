from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/market/full_universe_benchmark_assignment_policy.json"
REPORT_PATH = ROOT / "artifacts/certification/phase_3_6b_full_universe_benchmark_assignment_certification.json"
MINIMUM_TESTS = 421


def main() -> int:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    output = completed.stdout + completed.stderr
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if int(policy.get("required_record_count", 0)) != 3462:
        failures.append("REQUIRED_RECORD_COUNT_DRIFT")
    if not policy["controls"].get("all_input_records_preserved"):
        failures.append("PRESERVATION_CONTROL_MISSING")
    if not policy["controls"].get("no_arbitrary_target_universe_size"):
        failures.append("ARBITRARY_TRIM_CONTROL_MISSING")
    if policy["authority"].get("benchmark_qualified_universe_publication"):
        failures.append("QUALIFIED_UNIVERSE_PREMATURELY_AUTHORIZED")
    for key in ("relative_return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"):
        if policy["authority"].get(key):
            failures.append(f"PREMATURE_AUTHORITY_{key.upper()}")

    report = {
        "phase": "3.6b",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "required_records": policy["required_record_count"],
            "assignment_states": policy["required_assignment_states"],
            "full_universe_assignment_authorized": policy["authority"]["full_universe_benchmark_assignment"],
            "coverage_analysis_authorized": policy["authority"]["coverage_analysis"],
            "trimming_recommendation_authorized": policy["authority"]["trimming_recommendation"],
            "benchmark_qualified_universe_publication_authorized": policy["authority"]["benchmark_qualified_universe_publication"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
            "risk_analytics_authorized": policy["authority"]["risk_analytics"],
            "forecasting_authorized": policy["authority"]["forecasting"],
            "ranking_authorized": policy["authority"]["ranking"],
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b full-universe benchmark assignment certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
