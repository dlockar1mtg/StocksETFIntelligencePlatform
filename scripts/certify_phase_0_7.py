from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from foundation.validation.phase_0_integration import Phase0IntegrationError, validate_phase_0

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_0_completion_certification.json"
MINIMUM_TESTS = 56


def main() -> int:
    critical_failures: list[str] = []
    try:
        control = validate_phase_0(ROOT)
    except Phase0IntegrationError as exc:
        control = {}
        critical_failures.append(f"phase_0_integration_failure:{exc}")

    process = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = (process.stdout or "") + (process.stderr or "")
    match = re.search(r"Ran (\d+) tests?", output)
    tests_run = int(match.group(1)) if match else 0

    if process.returncode != 0:
        critical_failures.append("phase_0_regression_failure")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("insufficient_test_execution")
    if "ImportError" in output or "ModuleNotFoundError" in output:
        critical_failures.append("test_import_failure")

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "0.7",
        "certification": "phase_0_integrated_foundation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "production_authority_granted": False,
        "automatic_execution_authorized": False,
        "direct_uip_database_writes_authorized": False,
        "completed_subphases": control.get("required_subphases", []),
        "authorized_uses": control.get("authorized_uses", []),
        "unauthorized_uses": control.get("unauthorized_uses", []),
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(output, end="")
    print(f"\nPhase 0 integration certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
