from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/market/issuer_source_capture_pilot_policy.json"
REGISTRY_PATH = ROOT / "config/market/issuer_source_capture_pilot_registry.json"
REPORT_PATH = ROOT / "artifacts/certification/phase_3_6b_3a_issuer_source_capture_pilot_certification.json"


def main() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    tests_run = 0
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    failures = []
    if result.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < policy["minimum_cumulative_tests"]:
        failures.append("TEST_FLOOR_NOT_MET")
    if len(registry.get("records", {})) != policy["required_record_count"]:
        failures.append("PILOT_REGISTRY_COUNT_MISMATCH")
    report = {
        "phase": "3.6b.3a",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": policy["minimum_cumulative_tests"],
        "critical_failures": failures,
        "certification_result": {
            "pilot_record_count": len(registry.get("records", {})),
            "source_capture_authorized": policy["authority"]["authoritative_source_capture"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3a issuer source capture pilot certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT_PATH}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
