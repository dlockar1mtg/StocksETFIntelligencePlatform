from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6b_1_production_etf_taxonomy_evidence_certification.json"
MINIMUM_TESTS = 431


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    combined = completed.stdout + completed.stderr
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    policy = json.loads((ROOT / "config/market/production_etf_taxonomy_evidence_policy.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("REGRESSION_SUITE_FAILED")
    if tests_run < MINIMUM_TESTS:
        failures.append("TEST_FLOOR_NOT_MET")
    if policy["authority"]["production_taxonomy_classification"]:
        failures.append("PRODUCTION_TAXONOMY_PREMATURELY_AUTHORIZED")
    if policy["source"]["authoritative_taxonomy_source"]:
        failures.append("SECONDARY_SOURCE_MISLABELED_AUTHORITATIVE")
    report = {
        "phase": "3.6b.1",
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "certification_result": {
            "required_records": policy["required_record_count"],
            "taxonomy_evidence_collection_authorized": policy["authority"]["taxonomy_evidence_collection"],
            "coverage_analysis_authorized": policy["authority"]["taxonomy_evidence_coverage_analysis"],
            "production_taxonomy_classification_authorized": policy["authority"]["production_taxonomy_classification"],
            "source_is_authoritative_taxonomy": policy["source"]["authoritative_taxonomy_source"],
            "relative_return_calculation_authorized": policy["authority"]["relative_return_calculation"],
            "risk_analytics_authorized": policy["authority"]["risk_analytics"],
            "forecasting_authorized": policy["authority"]["forecasting"],
            "ranking_authorized": policy["authority"]["ranking"]
        },
        "critical_failures": failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.1 production ETF taxonomy evidence certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
