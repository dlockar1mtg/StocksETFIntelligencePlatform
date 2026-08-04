from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.analytics.contracts import AnalyticsContractError, validate_phase_2_1


MINIMUM_TESTS = 222
REPORT_PATH = ROOT / "artifacts/certification/phase_2_1_certification.json"


def main() -> int:
    failures: list[str] = []
    result: dict[str, object] = {}
    try:
        result = validate_phase_2_1(ROOT)
    except (AnalyticsContractError, OSError, json.JSONDecodeError) as exc:
        failures.append(f"ANALYTICS_CONTRACT_FAILURE: {exc}")

    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    tests_run = int(match.group(1)) if match else 0
    if completed.returncode != 0:
        failures.append("CUMULATIVE_REGRESSION_FAILURE")
    if tests_run < MINIMUM_TESTS:
        failures.append(f"TEST_FLOOR_NOT_MET: {tests_run} < {MINIMUM_TESTS}")

    status = "PASS" if not failures else "FAIL"
    report = {
        "phase": "2.1",
        "certification": "analytics_architecture_and_metric_contracts",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "contract_result": result,
        "production_metric_calculation_authorized": False,
        "scoring_authorized": False,
        "ranking_authorized": False,
        "forecasting_authorized": False,
        "recommendations_authorized": False,
        "portfolio_allocation_authorized": False,
        "uip_export_authorized": False,
        "automatic_execution_authorized": False,
        "direct_uip_database_writes_authorized": False,
        "test_output": output,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 2.1 certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
