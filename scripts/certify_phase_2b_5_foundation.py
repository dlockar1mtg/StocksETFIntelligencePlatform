from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_2b_5_foundation_certification.json"
MINIMUM_TESTS = 334


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

    policy = json.loads((ROOT / "config" / "market" / "phase_2b_foundation_certification_policy.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_total_records") != 4419:
        failures.append("TOTAL_RECORD_COUNT_DRIFT")
    if policy.get("phase_3_candidate_record_count") != 3462:
        failures.append("PHASE_3_CANDIDATE_COUNT_DRIFT")
    if policy.get("required_state_counts", {}).get("MARKET_DATA_PROVISIONAL") != 442:
        failures.append("PROVISIONAL_COUNT_DRIFT")
    if policy.get("provisional_records_preserved") is not True:
        failures.append("PROVISIONAL_PRESERVATION_WEAKENED")
    if policy.get("provisional_records_advance_to_phase_3") is not False:
        failures.append("PROVISIONAL_PROMOTION_ENABLED")
    if policy.get("phase_3_candidate_states") != ["MARKET_DATA_ELIGIBLE"]:
        failures.append("PHASE_3_ADMISSION_STATE_DRIFT")
    if policy.get("target_universe_size", "MISSING") is not None:
        failures.append("ARBITRARY_TARGET_INTRODUCED")

    report = {
        "phase": "2B.5",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certified_population": {
            "total_records": 4419,
            "phase_3_candidate_records": 3462,
            "provisional_preserved_not_advanced": 442,
            "research_only": 515,
            "required_seed_symbols": policy.get("required_seed_symbols"),
            "phase_3_candidate_states": policy.get("phase_3_candidate_states"),
            "selection_principle": policy.get("selection_principle"),
            "target_universe_size": policy.get("target_universe_size"),
        },
        "critical_failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 2B.5 market data foundation certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
