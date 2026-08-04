from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.market.market_data_screen import load_policy

REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_2b_1_market_data_screen_certification.json"
MINIMUM_TESTS = 286


def count_tests(output: str) -> int:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("Ran ") and " tests" in line:
            return int(line.split()[1])
    raise RuntimeError("Could not determine unittest count")


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    combined_output = completed.stdout + "\n" + completed.stderr
    tests_run = count_tests(combined_output)
    policy = load_policy()

    critical_failures: list[str] = []
    if completed.returncode != 0:
        critical_failures.append("CUMULATIVE_REGRESSION_FAILURE")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        critical_failures.append("SELECTION_PRINCIPLE_DRIFT")
    if policy.get("target_universe_size") is not None:
        critical_failures.append("ARBITRARY_TARGET_SIZE")
    if policy.get("preserve_input_universe") is not True:
        critical_failures.append("INPUT_UNIVERSE_NOT_PRESERVED")
    if policy.get("destructive_deletion_allowed") is not False:
        critical_failures.append("DESTRUCTIVE_DELETION_ALLOWED")
    if policy.get("required_seed_symbols") != ["VOO", "SCHD", "QQQM"]:
        critical_failures.append("SEED_SET_DRIFT")

    report = {
        "phase": "2",
        "subphase": "2B.1",
        "status": "PASS" if not critical_failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "selection_result": {
            "selection_principle": policy["selection_principle"],
            "target_universe_size": policy["target_universe_size"],
            "input_universe_preserved": policy["preserve_input_universe"],
            "destructive_deletion_allowed": policy["destructive_deletion_allowed"],
            "required_seed_symbols": policy["required_seed_symbols"],
        },
        "authority": policy["authority"],
        "critical_failures": critical_failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Phase 2B.1 market data screen certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
