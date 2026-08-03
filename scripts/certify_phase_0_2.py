from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_0_2_certification.json"
MIN_TESTS = 16


def run(command: list[str]) -> tuple[int, str]:
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return process.returncode, (process.stdout or "") + (process.stderr or "")


def main() -> int:
    env_code, env_output = run([sys.executable, "scripts/validate_environment.py"])
    test_code, test_output = run([
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_*.py",
        "-v",
    ])
    match = re.search(r"Ran (\d+) tests?", test_output)
    tests_run = int(match.group(1)) if match else 0
    critical_failures: list[str] = []
    if env_code != 0:
        critical_failures.append("environment_validation_failure")
    if test_code != 0:
        critical_failures.append("regression_test_failure")
    if tests_run < MIN_TESTS:
        critical_failures.append("minimum_test_count_not_met")

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "0.2",
        "certification": "repository_foundation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MIN_TESTS,
        "critical_failures": critical_failures,
        "authorized_uses": [
            "repository_scaffolding",
            "governance_validation",
            "contract_development",
            "research_only_development",
        ],
        "unauthorized_uses": [
            "certified_market_monitoring",
            "certified_asset_outlook",
            "certified_portfolio_action",
            "certified_contribution_allocation",
            "certified_uip_export",
            "automatic_execution",
        ],
        "environment_output": env_output,
        "test_output": test_output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(env_output, end="")
    print(test_output, end="")
    print(f"\nPhase 0.2 certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
