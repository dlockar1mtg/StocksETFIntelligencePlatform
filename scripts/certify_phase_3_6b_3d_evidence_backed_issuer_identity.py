from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6b_3d_evidence_backed_issuer_identity_certification.json"
POLICY_PATH = ROOT / "config/market/evidence_backed_issuer_identity_policy.json"
MINIMUM_TESTS = 492


def run_tests() -> int:
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v"], cwd=ROOT, text=True, capture_output=True)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(output)
    counts = [int(line.split()[1]) for line in output.splitlines() if line.startswith("Ran ") and " tests in " in line]
    count = counts[-1] if counts else 0
    if count < MINIMUM_TESTS:
        raise RuntimeError(f"Regression floor weakened: {count} < {MINIMUM_TESTS}")
    return count


def main() -> int:
    failures = []
    tests_run = 0
    policy = None
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        required = [
            ROOT / "foundation/market/evidence_backed_issuer_identity.py",
            ROOT / "scripts/run_phase_3_6b_3d_evidence_backed_issuer_identity.py",
            ROOT / "tests/market/test_phase_3_6b_3d_evidence_backed_issuer_identity.py",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing Phase 3.6b.3d files: {missing}")
        tests_run = run_tests()
    except Exception as exc:
        failures.append(str(exc))

    status = "PASS" if not failures else "FAIL"
    authority = policy.get("authority", {}) if policy else {}
    report = {
        "phase": "3.6b.3d",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "required_records": policy.get("required_full_population") if policy else None,
            "issuer_identity_acquisition_authorized": authority.get("issuer_identity_acquisition", False),
            "issuer_identity_coverage_analysis_authorized": authority.get("issuer_identity_coverage_analysis", False),
            "issuer_batch_planning_authorized": authority.get("issuer_batch_planning", False),
            "authoritative_source_capture_authorized": authority.get("authoritative_source_capture", False),
            "production_taxonomy_classification_authorized": authority.get("production_taxonomy_classification", False),
            "relative_return_calculation_authorized": authority.get("relative_return_calculation", False),
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3d evidence-backed issuer identity certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    for failure in failures:
        print(f"CRITICAL: {failure}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
