from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/market/priority_batch_route_discovery_pilot_policy.json"
REPORT_PATH = ROOT / "artifacts/certification/phase_3_6b_3h_priority_batch_route_discovery_pilot_certification.json"
MINIMUM_TESTS = 552


def main() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    tests_run = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    critical_failures: list[str] = []
    if completed.returncode != 0:
        critical_failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        critical_failures.append("REGRESSION_TEST_FLOOR_NOT_MET")
    if policy.get("policy_version") != "1.0.0":
        critical_failures.append("POLICY_VERSION_MISMATCH")
    if policy.get("authority", {}).get("route_discovery_pilot_manifest_build") is not True:
        critical_failures.append("PILOT_MANIFEST_BUILD_NOT_AUTHORIZED")

    for blocked in (
        "route_discovery_pilot_execution",
        "priority_batch_source_capture",
        "authoritative_source_capture",
        "production_taxonomy_classification",
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
        if policy.get("authority", {}).get(blocked) is not False:
            critical_failures.append(f"PREMATURE_AUTHORITY_{blocked.upper()}")

    report = {
        "phase": "3.6b.3h",
        "status": "PASS" if not critical_failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "route_discovery_pilot_manifest_build_authorized": policy["authority"]["route_discovery_pilot_manifest_build"],
            "route_discovery_pilot_execution_authorized": policy["authority"]["route_discovery_pilot_execution"],
            "priority_batch_source_capture_authorized": policy["authority"]["priority_batch_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
        "critical_failures": critical_failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3h priority batch route discovery pilot certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    if critical_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
