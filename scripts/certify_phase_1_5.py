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

from foundation.validation.phase_1_integration import Phase1IntegrationError, validate_phase_1


def main() -> int:
    output_dir = ROOT / "artifacts" / "certification"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "phase_1_completion_certification.json"

    critical_failures: list[str] = []
    integration_result: dict[str, object] = {}
    try:
        integration_result = validate_phase_1(ROOT)
    except (Phase1IntegrationError, OSError, json.JSONDecodeError) as exc:
        critical_failures.append(f"integration_validation_failure: {exc}")

    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    test_output = completed.stdout + completed.stderr
    match = re.search(r"Ran\s+(\d+)\s+tests?", test_output)
    tests_run = int(match.group(1)) if match else 0
    minimum_tests = 106

    if completed.returncode != 0:
        critical_failures.append("regression_failure")
    if tests_run < minimum_tests:
        critical_failures.append(f"test_floor_failure: {tests_run} < {minimum_tests}")

    status = "PASS" if not critical_failures else "FAIL"
    report = {
        "phase": "1.5",
        "certification": "integrated_phase_1_data_foundation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": minimum_tests,
        "critical_failures": critical_failures,
        "integration_result": integration_result,
        "certified_market_monitoring_authorized": False,
        "certified_analytics_authorized": False,
        "certified_recommendations_authorized": False,
        "certified_uip_export_authorized": False,
        "automatic_execution_authorized": False,
        "direct_uip_database_writes_authorized": False,
        "test_output": test_output,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Phase 1 integration certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {report_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
