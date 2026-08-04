from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_5_total_return_calculation_certification.json"
MINIMUM_TESTS = 394
EXPECTED = {"30d": 21, "90d": 63, "180d": 126, "1y": 252, "3y": 756, "5y": 1260}


def main() -> int:
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"], cwd=ROOT, text=True, capture_output=True)
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads((ROOT / "config" / "market" / "total_return_calculation_policy.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0: failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS: failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_record_count") != 3462: failures.append("RECORD_COUNT_DRIFT")
    if policy.get("return_basis") != "ADJUSTED_CLOSE_TOTAL_RETURN": failures.append("RETURN_BASIS_DRIFT")
    if policy.get("horizon_minimum_observations") != EXPECTED: failures.append("UIP_HORIZON_THRESHOLD_DRIFT")
    if policy.get("uip_horizon_contract") != list(EXPECTED): failures.append("UIP_HORIZON_ORDER_DRIFT")
    if policy.get("legacy_horizon_aliases") != {"1m": "30d", "3m": "90d"}: failures.append("LEGACY_ALIAS_DRIFT")
    if policy.get("authority", {}).get("return_calculation") is not True: failures.append("RETURN_CALCULATION_NOT_AUTHORIZED")
    forbidden = ["risk_analytics", "benchmark_comparison", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
    if any(policy.get("authority", {}).get(key) is not False for key in forbidden): failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")
    report = {"phase": "3.5a", "status": "PASS" if not failures else "FAIL", "tests_run": tests_run, "minimum_tests_required": MINIMUM_TESTS, "calculation_result": {"required_records": 3462, "return_basis": policy.get("return_basis"), "uip_horizon_contract": policy.get("uip_horizon_contract"), "horizon_minimum_observations": policy.get("horizon_minimum_observations"), "annualized_horizons": policy.get("annualized_horizons"), "return_calculation_authorized": policy.get("authority", {}).get("return_calculation"), "risk_analytics_authorized": policy.get("authority", {}).get("risk_analytics"), "benchmark_comparison_authorized": policy.get("authority", {}).get("benchmark_comparison"), "forecasting_authorized": policy.get("authority", {}).get("forecasting")}, "critical_failures": failures}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.5a UIP horizon alignment certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
