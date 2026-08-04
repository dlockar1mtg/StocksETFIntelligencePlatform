from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from foundation.market.historical_data_authority import load_policy, validate_contract_registration

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_1_historical_data_authority_certification.json"
MINIMUM_TESTS = 346


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

    failures: list[str] = []
    try:
        policy = load_policy()
        validate_contract_registration()
    except Exception as exc:
        policy = {}
        failures.append(f"POLICY_OR_CONTRACT_INVALID:{exc}")

    if completed.returncode != 0:
        failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_candidate_count") != 3462:
        failures.append("PHASE_3_CANDIDATE_COUNT_DRIFT")
    if policy.get("provisional_candidates_allowed") is not False:
        failures.append("PROVISIONAL_CANDIDATES_AUTHORIZED")
    if policy.get("return_basis", {}).get("primary_basis") != "TOTAL_RETURN":
        failures.append("TOTAL_RETURN_BASIS_DRIFT")

    report = {
        "phase": "3.1",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "authority_result": {
            "candidate_records": policy.get("required_candidate_count"),
            "required_candidate_state": policy.get("required_candidate_state"),
            "provisional_candidates_allowed": policy.get("provisional_candidates_allowed"),
            "primary_provider_id": policy.get("provider_authority", {}).get("primary_provider_id"),
            "return_basis": policy.get("return_basis", {}).get("primary_basis"),
            "historical_collection_authorized": policy.get("authority", {}).get("historical_data_collection"),
            "return_calculation_authorized": policy.get("authority", {}).get("return_calculation"),
            "risk_analytics_authorized": policy.get("authority", {}).get("risk_analytics"),
            "forecasting_authorized": policy.get("authority", {}).get("forecasting"),
        },
        "critical_failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.1 historical data authority certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
