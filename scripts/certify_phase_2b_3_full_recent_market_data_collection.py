from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


MINIMUM_TESTS = 310
REPORT_PATH = Path("artifacts/certification/phase_2b_3_full_recent_market_data_collection_certification.json")


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    marker = "Ran "
    tests_run = 0
    for line in output.splitlines():
        if line.startswith(marker) and " tests" in line:
            tests_run = int(line.split()[1])

    policy = json.loads(
        Path("config/sources/full_recent_market_data_collection_policy.json").read_text(encoding="utf-8")
    )
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("expected_input_record_count") != 4419:
        failures.append("ACTIVE_UNIVERSE_COUNT_DRIFT")
    if policy.get("required_seed_symbols") != ["VOO", "SCHD", "QQQM"]:
        failures.append("SEED_SET_DRIFT")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        failures.append("SELECTION_PRINCIPLE_DRIFT")
    if policy.get("target_universe_size") is not None:
        failures.append("ARBITRARY_TARGET_SIZE")
    if policy.get("preserve_all_input_records") is not True:
        failures.append("INPUT_PRESERVATION_WEAKENED")
    if policy.get("destructive_deletion_allowed") is not False:
        failures.append("DESTRUCTIVE_DELETION_ENABLED")
    if any(bool(value) for value in policy.get("authority", {}).values()):
        failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")

    report = {
        "phase": "2B.3",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "selection_result": {
            "expected_input_record_count": policy.get("expected_input_record_count"),
            "required_seed_symbols": policy.get("required_seed_symbols"),
            "selection_principle": policy.get("selection_principle"),
            "target_universe_size": policy.get("target_universe_size"),
            "preserve_all_input_records": policy.get("preserve_all_input_records"),
            "destructive_deletion_allowed": policy.get("destructive_deletion_allowed"),
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 2B.3 full recent market data collection certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH.resolve()}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
