from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_1_6_5_certification.json"
MINIMUM_TESTS = 154


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
        "phase": "1.6.5",
        "certification": "governed_etf_data_coverage_and_analytics_eligibility",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "minimum_price_history_trading_days": 252,
        "missing_core_domain_is_eligible": False,
        "stale_core_evidence_is_eligible": False,
        "critical_conflict_is_eligible": False,
        "new_funds_may_be_provisional": True,
        "provisional_status_grants_certified_analytics": False,
        "specialized_products_require_strategy_specific_coverage": True,
        "analytics_eligibility_grants_recommendation_authority": False,
        "analytics_eligibility_grants_portfolio_suitability": False,
        "automatic_execution_authorized": False,
        "snapshot_immutable": True,
        "test_output": output,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 1.6.5 certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
