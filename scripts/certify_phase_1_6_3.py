from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_1_6_3_certification.json"
MINIMUM_TESTS = 135


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = f"{result.stdout}{result.stderr}"
    tests_run = output.count(" ... ok") + output.count(" ... FAIL") + output.count(" ... ERROR")
    failures: list[str] = []
    if result.returncode != 0:
        failures.append("Cumulative regression suite failed")
    if tests_run < MINIMUM_TESTS:
        failures.append(f"Regression floor weakened: {tests_run} < {MINIMUM_TESTS}")

    report = {
        "phase": "1.6.3",
        "certification": "robinhood_broker_eligibility_model",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "broker_id": "ROBINHOOD-US",
        "eligibility_is_time_dependent": True,
        "listing_does_not_imply_broker_eligibility": True,
        "unknown_status_is_eligible": False,
        "stale_status_is_eligible": False,
        "conflicted_status_is_eligible": False,
        "capabilities_are_independent": True,
        "whole_share_support_required": True,
        "fractional_share_support_required": False,
        "recurring_investment_support_required": False,
        "dividend_reinvestment_support_required": False,
        "snapshot_immutable": True,
        "certified_market_monitoring_authorized": False,
        "certified_analytics_authorized": False,
        "certified_recommendations_authorized": False,
        "certified_uip_export_authorized": False,
        "automatic_execution_authorized": False,
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 1.6.3 certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
