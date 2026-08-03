from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_1_4_certification.json"
MINIMUM_TESTS = 98


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = result.stdout + result.stderr
    tests_run = output.count(" ... ok") + output.count(" ... FAIL") + output.count(" ... ERROR")
    failures: list[str] = []
    if result.returncode != 0:
        failures.append("regression_failure")
    if tests_run < MINIMUM_TESTS:
        failures.append("test_floor_failure")

    report = {
        "phase": "1.4",
        "certification": "evidence_quality_freshness_quarantine_foundation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certified_market_monitoring_authorized": False,
        "certified_analytics_authorized": False,
        "direct_uip_database_writes_authorized": False,
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Phase 1.4 certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
