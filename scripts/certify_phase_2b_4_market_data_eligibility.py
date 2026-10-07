from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_2b_4_market_data_eligibility_certification.json"
MINIMUM_TESTS = 322


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

    policy = json.loads((ROOT / "config" / "market" / "market_data_eligibility_classification_policy.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_input_record_count") != 4419:
        failures.append("ACTIVE_UNIVERSE_COUNT_DRIFT")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        failures.append("SELECTION_PRINCIPLE_DRIFT")
    if policy.get("target_universe_size", "MISSING") is not None:
        failures.append("ARBITRARY_TARGET_INTRODUCED")

    report = {
        "phase": "2B.4",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "selection_result": {
            "expected_input_record_count": 4419,
            "selection_principle": policy.get("selection_principle"),
            "target_universe_size": policy.get("target_universe_size"),
            "preserve_all_input_records": policy.get("preserve_all_input_records"),
            "required_seed_symbols": policy.get("required_seed_symbols"),
        },
        "critical_failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 2B.4 market data eligibility certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
