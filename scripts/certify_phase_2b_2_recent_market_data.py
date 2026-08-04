from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "artifacts/certification/phase_2b_2_recent_market_data_certification.json"
MINIMUM_TESTS = 298


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    combined = completed.stdout + "\n" + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    policy = json.loads((ROOT / "config/sources/recent_market_data_acquisition_policy.json").read_text(encoding="utf-8"))
    critical_failures: list[str] = []
    if completed.returncode != 0:
        critical_failures.append("REGRESSION_FAILURE")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("TEST_FLOOR_FAILURE")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE" or policy.get("target_universe_size") is not None:
        critical_failures.append("ARBITRARY_UNIVERSE_SIZE")
    if policy.get("required_seed_symbols") != ["VOO", "SCHD", "QQQM"]:
        critical_failures.append("SEED_DRIFT")
    authority = policy.get("authority", {})
    for key in ("full_history_collection", "analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes"):
        if authority.get(key) is not False:
            critical_failures.append(f"AUTHORITY_EXPANSION:{key}")

    report = {
        "phase": "2B.2",
        "status": "PASS" if not critical_failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "selection_result": {
            "selection_principle": policy.get("selection_principle"),
            "target_universe_size": policy.get("target_universe_size"),
            "preserve_all_input_records": policy.get("preserve_all_input_records"),
            "required_seed_symbols": policy.get("required_seed_symbols"),
        },
        "critical_failures": critical_failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 2B.2 recent market data certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
