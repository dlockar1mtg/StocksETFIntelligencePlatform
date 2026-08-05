from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "market" / "priority_batch_controlled_source_capture_execution_policy.json"
REPORT_PATH = ROOT / "artifacts" / "certification" / "phase_3_6b_3m_priority_batch_controlled_source_capture_execution_certification.json"
MINIMUM_TESTS = 602


def main() -> int:
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    tests_run = 0
    for line in combined.splitlines():
        stripped = line.strip()
        if stripped.startswith("Ran ") and " tests" in stripped:
            try:
                tests_run = int(stripped.split()[1])
            except (IndexError, ValueError):
                pass

    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("CUMULATIVE_REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("REGRESSION_TEST_FLOOR_NOT_MET")

    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        policy = {}
        failures.append(f"POLICY_UNREADABLE:{type(exc).__name__}")

    if policy.get("phase") != "3.6b.3m":
        failures.append("POLICY_PHASE_DRIFT")
    if int(policy.get("required_record_count", -1)) != 347:
        failures.append("REQUIRED_RECORD_COUNT_DRIFT")
    if policy.get("required_route_type") != "SEC_SERIES_CLASS_FILING_DISCOVERY":
        failures.append("AUTHORIZED_ROUTE_DRIFT")
    authority = policy.get("authority", {})
    if authority.get("priority_batch_source_capture") is not True:
        failures.append("CONTROLLED_CAPTURE_NOT_AUTHORIZED")
    if authority.get("controlled_capture_execution") is not True:
        failures.append("CONTROLLED_EXECUTION_NOT_AUTHORIZED")
    for blocked in (
        "capture_ledger_certification",
        "authoritative_source_capture",
        "taxonomy_evidence_normalization",
        "production_taxonomy_classification",
        "production_taxonomy_certification",
        "benchmark_qualified_universe_publication",
        "relative_return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    ):
        if authority.get(blocked) is not False:
            failures.append(f"PREMATURE_AUTHORITY:{blocked}")

    report = {
        "phase": "3.6b.3m",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "priority_batch_source_capture_authorized": authority.get("priority_batch_source_capture", False),
            "controlled_capture_execution_authorized": authority.get("controlled_capture_execution", False),
            "capture_ledger_review_authorized": authority.get("capture_ledger_review", False),
            "capture_ledger_certification_authorized": authority.get("capture_ledger_certification", False),
            "taxonomy_evidence_normalization_authorized": authority.get("taxonomy_evidence_normalization", False),
            "production_taxonomy_classification_authorized": authority.get("production_taxonomy_classification", False),
            "relative_return_calculation_authorized": authority.get("relative_return_calculation", False),
            "automatic_execution_authorized": authority.get("automatic_execution", False),
        },
        "critical_failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Phase 3.6b.3m priority batch controlled source capture execution certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
