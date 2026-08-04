from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation.universe.structural_identity_resolution import load_policy

REPORT = ROOT / "artifacts" / "certification" / "phase_2a_4_identity_resolution_certification.json"
MINIMUM_TESTS = 264


def run_tests() -> int:
    command = [
        sys.executable, "-m", "unittest", "discover",
        "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(output)
    count = 0
    for line in output.splitlines():
        if line.startswith("Ran ") and " tests in " in line:
            count = int(line.split()[1])
    if count < MINIMUM_TESTS:
        raise RuntimeError(f"Regression floor weakened: {count} < {MINIMUM_TESTS}")
    return count


def main() -> int:
    failures: list[str] = []
    tests_run = 0
    policy = None
    try:
        policy = load_policy()
        required = [
            ROOT / "foundation" / "universe" / "structural_identity_resolution.py",
            ROOT / "scripts" / "run_phase_2a_4_identity_resolution.py",
            ROOT / "tests" / "universe" / "test_phase_2a_4_identity_resolution.py",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing Phase 2A.4 files: {missing}")
        tests_run = run_tests()
    except Exception as exc:
        failures.append(str(exc))

    status = "PASS" if not failures else "FAIL"
    report = {
        "phase": "2A.4",
        "certification_type": "STRUCTURAL_IDENTITY_RESOLUTION_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "selection_result": {
            "selection_principle": "EVIDENCE_DETERMINES_SIZE",
            "target_universe_size": None,
            "full_discovery_universe_preserved": True,
            "destructive_deletion_allowed": False,
        },
        "authorized": {
            "identity_resolution_development": status == "PASS",
            "unmatched_attribution_development": status == "PASS",
        },
        "unauthorized": {
            "production_data_certification": True,
            "analytics": True,
            "forecasting": True,
            "ranking": True,
            "recommendations": True,
            "portfolio_allocation": True,
            "uip_export": True,
            "automatic_execution": True,
            "direct_uip_database_writes": True,
        },
        "policy_version": policy["policy_version"] if policy else None,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 2A.4 identity resolution certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    for failure in failures:
        print(f"CRITICAL: {failure}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
