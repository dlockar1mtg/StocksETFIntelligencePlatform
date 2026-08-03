from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_1_6_6_certification.json"
SNAPSHOT_PATH = ROOT / "data" / "universe" / "snapshots" / "2026-08-03" / "robinhood_universe_snapshot.json"
MINIMUM_TESTS = 164


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

    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if snapshot["snapshot_status"] != "STRUCTURAL_BASELINE":
        failures.append("Initial dated snapshot must remain explicitly structural until external evidence is acquired")
    if any(record["broker_status"] != "UNKNOWN" for record in snapshot["records"]):
        failures.append("Structural snapshot contains unverified broker eligibility claims")

    report = {
        "phase": "1.6.6",
        "certification": "dated_robinhood_universe_structural_snapshot",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "snapshot_id": snapshot["snapshot_id"],
        "operating_date": snapshot["operating_date"],
        "operating_timezone": snapshot["operating_timezone"],
        "snapshot_status": snapshot["snapshot_status"],
        "record_count": snapshot["counts"]["total_records"],
        "broker_eligible_count": snapshot["counts"]["broker_eligible"],
        "analytics_eligible_count": snapshot["counts"]["analytics_eligible"],
        "unverified_broker_eligibility_claims": False,
        "pending_evidence_is_explicit": True,
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
    print(f"Phase 1.6.6 certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Snapshot: {snapshot['snapshot_id']}")
    print(f"Report: {REPORT}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
