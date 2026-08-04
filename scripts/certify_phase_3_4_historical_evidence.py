from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_4_historical_evidence_certification.json"
MINIMUM_TESTS = 394
EXPECTED = {"30d": 21, "90d": 63, "180d": 126, "1y": 252, "3y": 756, "5y": 1260}


def main() -> int:
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"], cwd=ROOT, text=True, capture_output=True)
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads((ROOT / "config" / "market" / "historical_evidence_certification_policy.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0: failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS: failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_record_count") != 3462: failures.append("RECORD_COUNT_DRIFT")
    if policy.get("required_provider_data_granularity") != "1d": failures.append("DAILY_GRANULARITY_NOT_REQUIRED")
    if policy.get("horizon_minimum_observations") != EXPECTED: failures.append("UIP_HORIZON_THRESHOLDS_DRIFT")
    if policy.get("uip_horizon_contract") != list(EXPECTED): failures.append("UIP_HORIZON_ORDER_DRIFT")
    if policy.get("legacy_horizon_aliases") != {"1m": "30d", "3m": "90d"}: failures.append("LEGACY_ALIAS_DRIFT")
    preservation = policy.get("preservation", {})
    if preservation.get("all_input_records_preserved") is not True or preservation.get("shorter_history_records_not_deleted") is not True:
        failures.append("NON_DESTRUCTIVE_PRESERVATION_WEAKENED")
    forbidden = ["return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
    if any(policy.get("authority", {}).get(key) is not False for key in forbidden): failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")
    report = {"phase": "3.4", "status": "PASS" if not failures else "FAIL", "tests_run": tests_run, "minimum_tests_required": MINIMUM_TESTS, "certification_result": {"required_records": 3462, "uip_horizon_contract": policy.get("uip_horizon_contract"), "horizon_minimum_observations": policy.get("horizon_minimum_observations"), "return_calculation_authorized": policy.get("authority", {}).get("return_calculation")}, "critical_failures": failures}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.4 historical evidence certification control: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
