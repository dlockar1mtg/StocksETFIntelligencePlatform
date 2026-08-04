from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "certification" / "phase_3_6b_3e_issuer_batch_plan_rebuild_certification.json"
POLICY_PATH = ROOT / "config" / "market" / "issuer_batch_plan_rebuild_policy.json"
MINIMUM_TESTS = 522


def run_tests() -> int:
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v"]
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
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        required = [
            ROOT / "foundation" / "market" / "issuer_batch_plan_rebuild.py",
            ROOT / "scripts" / "run_phase_3_6b_3e_issuer_batch_plan_rebuild.py",
            ROOT / "tests" / "market" / "test_phase_3_6b_3e_issuer_batch_plan_rebuild.py",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing Phase 3.6b.3e files: {missing}")
        tests_run = run_tests()
    except Exception as exc:
        failures.append(str(exc))

    status = "PASS" if not failures else "FAIL"
    authority = policy.get("authority", {}) if policy else {}
    report = {
        "phase": "3.6b.3e",
        "certification_type": "ISSUER_BATCH_PLAN_REBUILD_CONTROL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "issuer_batch_plan_rebuild_authorized": status == "PASS" and authority.get("issuer_batch_plan_rebuild") is True,
            "coverage_prioritization_authorized": status == "PASS" and authority.get("coverage_prioritization") is True,
            "authoritative_source_capture_authorized": False,
            "production_taxonomy_classification_authorized": False,
            "relative_return_calculation_authorized": False,
        },
        "policy_version": policy.get("policy_version") if policy else None,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3e issuer batch plan rebuild certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    for failure in failures:
        print(f"CRITICAL: {failure}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
