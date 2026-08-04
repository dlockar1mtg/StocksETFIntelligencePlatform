from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/market/authoritative_etf_taxonomy_normalization_policy.json"
REGISTRY_PATH = ROOT / "config/market/authoritative_etf_taxonomy_registry.json"
REPORT_PATH = ROOT / "artifacts/certification/phase_3_6b_2_authoritative_etf_taxonomy_normalization_certification.json"
MINIMUM_TESTS = 442


def main() -> int:
    failures: list[str] = []
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    command = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    tests_run = 0
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Ran ") and " tests" in line:
            try:
                tests_run = int(line.split()[1])
            except Exception:
                pass

    if completed.returncode != 0:
        failures.append("CUMULATIVE_TEST_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("MINIMUM_TEST_FLOOR_NOT_MET")
    if policy.get("required_record_count") != 3462:
        failures.append("REQUIRED_RECORD_COUNT_DRIFTED")
    if registry.get("status") != "CONTROL_BASELINE_REQUIRES_FULL_POPULATION":
        failures.append("REGISTRY_STATUS_DRIFTED")
    if policy["authority"].get("taxonomy_normalization") is not True:
        failures.append("TAXONOMY_NORMALIZATION_NOT_AUTHORIZED")
    for key in (
        "production_taxonomy_classification",
        "production_taxonomy_certification",
        "benchmark_qualified_universe_publication",
        "relative_return_calculation",
        "risk_analytics",
        "forecasting",
        "ranking",
        "recommendations",
    ):
        if policy["authority"].get(key) is not False:
            failures.append(f"{key.upper()}_PREMATURELY_AUTHORIZED")

    report = {
        "phase": "3.6b.2",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "required_records": 3462,
            "registry_status": registry.get("status"),
            "registry_entry_count": len(registry.get("records", {})),
            "taxonomy_normalization_authorized": policy["authority"]["taxonomy_normalization"],
            "taxonomy_coverage_analysis_authorized": policy["authority"]["taxonomy_coverage_analysis"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "production_taxonomy_certification_authorized": policy["authority"]["production_taxonomy_certification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.2 authoritative taxonomy normalization certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
