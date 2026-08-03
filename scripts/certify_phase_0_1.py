import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "tests" / "governance"
ARTIFACT_DIR = ROOT / "artifacts" / "certification"
REPORT_PATH = ARTIFACT_DIR / "phase_0_1_certification.json"
EXPECTED_MINIMUM_TESTS = 8


def run_tests() -> tuple[int, str, int]:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(TEST_ROOT),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = (process.stdout or "") + (process.stderr or "")
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    tests_run = int(match.group(1)) if match else 0

    return_code = process.returncode
    if tests_run < EXPECTED_MINIMUM_TESTS:
        return_code = return_code or 5
        output += (
            f"\nCERTIFICATION GUARD FAILURE: expected at least "
            f"{EXPECTED_MINIMUM_TESTS} tests, but discovered {tests_run}.\n"
        )

    return return_code, output, tests_run


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return_code, output, tests_run = run_tests()
    status = "PASS" if return_code == 0 else "FAIL"
    critical_failures: list[str] = []
    if tests_run < EXPECTED_MINIMUM_TESTS:
        critical_failures.append("insufficient_test_discovery")
    if return_code != 0:
        critical_failures.append("governance_regression_test_failure")

    report = {
        "phase": "0.1",
        "certification": "governance_authority_package",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": EXPECTED_MINIMUM_TESTS,
        "critical_failures": sorted(set(critical_failures)),
        "authorized_uses": [
            "repository_scaffolding",
            "governance_validation",
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
        "test_output": output,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output, end="")
    print(f"\nPhase 0.1 certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
