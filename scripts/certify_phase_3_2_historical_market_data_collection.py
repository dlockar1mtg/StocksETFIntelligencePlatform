from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_2_historical_market_data_collection_certification.json"
MINIMUM_TESTS = 358


def main() -> int:
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"], cwd=ROOT, text=True, capture_output=True)
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads((ROOT / "config" / "sources" / "historical_market_data_collection_policy.json").read_text(encoding="utf-8"))
    failures = []
    if completed.returncode != 0:
        failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_candidate_count") != 3462:
        failures.append("CANDIDATE_COUNT_DRIFT")
    if policy.get("provisional_candidates_allowed") is not False:
        failures.append("PROVISIONAL_PROMOTION")
    if policy.get("pilot", {}).get("symbols") != ["VOO", "SCHD", "QQQM"]:
        failures.append("PILOT_SEED_DRIFT")
    if policy.get("pilot", {}).get("full_universe_collection_authorized_before_pilot_review") is not False:
        failures.append("FULL_COLLECTION_PREMATURELY_AUTHORIZED")
    forbidden = ["return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
    if any(policy.get("authority", {}).get(key) is not False for key in forbidden):
        failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")
    report = {
        "phase": "3.2",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "collection_result": {
            "candidate_records": 3462,
            "required_candidate_state": policy.get("required_candidate_state"),
            "provisional_candidates_allowed": policy.get("provisional_candidates_allowed"),
            "provider_id": policy.get("provider_id"),
            "range": policy.get("range"),
            "interval": policy.get("interval"),
            "pilot_symbols": policy.get("pilot", {}).get("symbols"),
            "full_universe_collection_authorized": policy.get("pilot", {}).get("full_universe_collection_authorized_before_pilot_review"),
            "return_calculation_authorized": policy.get("authority", {}).get("return_calculation"),
            "risk_analytics_authorized": policy.get("authority", {}).get("risk_analytics"),
            "forecasting_authorized": policy.get("authority", {}).get("forecasting")
        },
        "critical_failures": failures
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.2 historical market data collection certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
