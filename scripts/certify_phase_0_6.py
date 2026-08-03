from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_0_6_certification.json"
MINIMUM_TESTS = 48


def main() -> int:
    process = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = (process.stdout or "") + (process.stderr or "")
    match = re.search(r"Ran (\d+) tests?", output)
    tests_run = int(match.group(1)) if match else 0
    critical_failures: list[str] = []
    if process.returncode != 0:
        critical_failures.append("market_standard_regression_failure")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("insufficient_test_execution")
    if "ModuleNotFoundError" in output or "ImportError" in output:
        critical_failures.append("test_import_failure")
    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "0.6",
        "certification": "calendar_benchmark_corporate_action_standards",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "authorized_uses": ["market_standard_development", "calendar_validation", "return_standard_validation", "corporate_action_validation", "research_only_development"],
        "unauthorized_uses": ["certified_market_monitoring", "certified_asset_outlook", "certified_portfolio_action", "certified_contribution_allocation", "certified_uip_export", "automatic_execution"],
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output, end="")
    print(f"\nPhase 0.6 certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
