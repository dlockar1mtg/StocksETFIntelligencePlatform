from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_3_full_historical_collection_certification.json"
MINIMUM_TESTS = 370


def main() -> int:
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"], cwd=ROOT, text=True, capture_output=True)
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads((ROOT / "config" / "market" / "full_historical_collection_authorization_policy.json").read_text(encoding="utf-8"))
    failures = []
    if completed.returncode != 0: failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS: failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_candidate_count") != 3462: failures.append("CANDIDATE_COUNT_DRIFT")
    if policy.get("provisional_candidates_allowed") is not False: failures.append("PROVISIONAL_PROMOTION")
    if policy.get("full_collection", {}).get("authorized") is not True: failures.append("FULL_COLLECTION_NOT_AUTHORIZED")
    if policy.get("full_collection", {}).get("provider_data_granularity_required") != "1d": failures.append("DAILY_GRANULARITY_NOT_REQUIRED")
    if policy.get("pilot_review", {}).get("required") is not True: failures.append("PILOT_REVIEW_NOT_REQUIRED")
    forbidden = ["return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"]
    if any(policy.get("authority", {}).get(key) is not False for key in forbidden): failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")
    report = {
        "phase": "3.3",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "authorization_result": {
            "candidate_records": policy.get("required_candidate_count"),
            "required_candidate_state": policy.get("required_candidate_state"),
            "provisional_candidates_allowed": policy.get("provisional_candidates_allowed"),
            "pilot_review_required": policy.get("pilot_review", {}).get("required"),
            "full_universe_collection_authorized": policy.get("full_collection", {}).get("authorized"),
            "required_provider_granularity": policy.get("full_collection", {}).get("provider_data_granularity_required"),
            "completion_attestation_required": policy.get("full_collection", {}).get("completion_attestation_required"),
            "return_calculation_authorized": policy.get("authority", {}).get("return_calculation"),
            "risk_analytics_authorized": policy.get("authority", {}).get("risk_analytics"),
            "forecasting_authorized": policy.get("authority", {}).get("forecasting")
        },
        "critical_failures": failures
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.3 full historical collection certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
