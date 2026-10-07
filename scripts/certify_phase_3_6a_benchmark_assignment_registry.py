from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6a_benchmark_assignment_registry_certification.json"
MINIMUM_TESTS = 412


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py", "-v"],
        cwd=ROOT, text=True, capture_output=True,
    )
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])

    policy = json.loads((ROOT / "config/market/benchmark_assignment_registry_policy.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "config/market/benchmark_assignment_rules.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("CUMULATIVE_TESTS_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy.get("required_record_count") != 3462:
        failures.append("RECORD_COUNT_DRIFT")
    if policy.get("assignment_states") != ["BENCHMARK_ASSIGNED", "BENCHMARK_UNASSIGNED", "BENCHMARK_UNSUPPORTED", "BENCHMARK_CONFLICTED"]:
        failures.append("ASSIGNMENT_STATES_DRIFT")
    if rules.get("status") != "CONTROL_BASELINE":
        failures.append("RULE_REGISTRY_STATUS_DRIFT")
    required_true = ["benchmark_taxonomy", "benchmark_assignment_registry"]
    if any(policy.get("authority", {}).get(item) is not True for item in required_true):
        failures.append("ASSIGNMENT_AUTHORITY_MISSING")
    forbidden = ["relative_return_calculation", "risk_analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution"]
    if any(policy.get("authority", {}).get(item) is not False for item in forbidden):
        failures.append("DOWNSTREAM_AUTHORITY_EXPANDED")

    report = {
        "phase": "3.6a",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "required_records": policy.get("required_record_count"),
            "assignment_states": policy.get("assignment_states"),
            "supported_benchmark_class_count": len(policy.get("supported_benchmark_classes", [])),
            "rule_registry_status": rules.get("status"),
            "benchmark_taxonomy_authorized": policy.get("authority", {}).get("benchmark_taxonomy"),
            "benchmark_assignment_registry_authorized": policy.get("authority", {}).get("benchmark_assignment_registry"),
            "relative_return_calculation_authorized": policy.get("authority", {}).get("relative_return_calculation"),
            "risk_analytics_authorized": policy.get("authority", {}).get("risk_analytics"),
            "forecasting_authorized": policy.get("authority", {}).get("forecasting"),
            "ranking_authorized": policy.get("authority", {}).get("ranking"),
        },
        "critical_failures": failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6a benchmark assignment registry certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
