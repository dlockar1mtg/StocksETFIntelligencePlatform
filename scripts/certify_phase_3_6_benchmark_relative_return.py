from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_6_benchmark_relative_return_certification.json"
MINIMUM_TESTS = 402
EXPECTED_HORIZONS = ["30d", "90d", "180d", "1y", "3y", "5y"]


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads((ROOT / "config" / "market" / "benchmark_relative_return_policy.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("uip_horizon_contract") != EXPECTED_HORIZONS:
        failures.append("UIP_HORIZON_CONTRACT_DRIFT")
    if policy.get("required_return_basis") != "ADJUSTED_CLOSE_TOTAL_RETURN":
        failures.append("RETURN_BASIS_DRIFT")
    controls = policy.get("controls", {})
    if controls.get("same_start_date_required") is not True or controls.get("same_end_date_required") is not True:
        failures.append("MATCHED_WINDOW_CONTROL_WEAKENED")
    if controls.get("missing_benchmark_must_not_be_imputed") is not True:
        failures.append("MISSING_BENCHMARK_IMPUTATION_ALLOWED")
    authority = policy.get("authority", {})
    for key in ("benchmark_assignment", "benchmark_comparison", "relative_return_calculation"):
        if authority.get(key) is not True:
            failures.append(f"{key.upper()}_NOT_AUTHORIZED")
    forbidden = ["risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
    if any(authority.get(key) is not False for key in forbidden):
        failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")
    report = {
        "phase": "3.6",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "uip_horizon_contract": policy.get("uip_horizon_contract"),
            "return_basis": policy.get("required_return_basis"),
            "benchmark_assignment_authorized": authority.get("benchmark_assignment"),
            "benchmark_comparison_authorized": authority.get("benchmark_comparison"),
            "relative_return_calculation_authorized": authority.get("relative_return_calculation"),
            "risk_analytics_authorized": authority.get("risk_analytics"),
            "forecasting_authorized": authority.get("forecasting"),
            "ranking_authorized": authority.get("ranking"),
        },
        "critical_failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6 benchmark relative-return certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
