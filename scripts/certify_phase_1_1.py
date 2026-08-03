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

from foundation.validation.provider_contracts import ProviderContractError, validate_phase_1_1

REPORT = ROOT / "artifacts" / "certification" / "phase_1_1_certification.json"
MINIMUM_TESTS = 74


def main() -> int:
    critical_failures: list[str] = []
    try:
        validate_phase_1_1(ROOT)
    except ProviderContractError as exc:
        critical_failures.append(f"provider_contract_failure:{exc}")

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
        critical_failures.append("regression_failure")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("insufficient_test_execution")
    if "ImportError" in output or "ModuleNotFoundError" in output:
        critical_failures.append("test_import_failure")

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "1.1",
        "certification": "provider_contract_foundation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": critical_failures,
        "certified_market_monitoring_authorized": False,
        "certified_analytics_authorized": False,
        "direct_uip_database_writes_authorized": False,
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(output, end="")
    print(f"\nPhase 1.1 certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
