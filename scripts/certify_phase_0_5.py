from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_0_5_certification.json"
MINIMUM_TESTS = 40


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
        critical_failures.append("security_master_regression_failure")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("insufficient_test_execution")
    if "ModuleNotFoundError" in output or "_FailedTest" in output:
        critical_failures.append("test_import_failure")
    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "0.5",
        "certification": "security_master_etf_universe_foundation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "authorized_uses": ["security_master_development", "universe_governance_development", "eligibility_validation", "research_only_development"],
        "unauthorized_uses": ["certified_market_monitoring", "certified_asset_outlook", "certified_portfolio_action", "certified_contribution_allocation", "certified_uip_export", "automatic_execution"],
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output, end="")
    print(f"\nPhase 0.5 certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
