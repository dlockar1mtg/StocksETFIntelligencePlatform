from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/certification/phase_3_6b_3d_1_sec_registrant_name_enrichment_certification.json"
MINIMUM_TESTS = 502


def main() -> int:
    failures = []
    tests_run = 0
    policy = None
    try:
        policy = json.loads((ROOT / "config/market/sec_registrant_name_enrichment_policy.json").read_text(encoding="utf-8"))
        required = [
            ROOT / "foundation/market/sec_registrant_name_enrichment.py",
            ROOT / "scripts/run_phase_3_6b_3d_1_sec_registrant_name_enrichment.py",
            ROOT / "tests/market/test_phase_3_6b_3d_1_sec_registrant_name_enrichment.py",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing required files: {missing}")
        completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-t", str(ROOT), "-p", "test_*.py", "-v"], cwd=ROOT, text=True, capture_output=True)
        output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise RuntimeError(output)
        for line in output.splitlines():
            if line.startswith("Ran ") and " tests in " in line:
                tests_run = int(line.split()[1])
        if tests_run < MINIMUM_TESTS:
            raise RuntimeError(f"Regression floor weakened: {tests_run} < {MINIMUM_TESTS}")
    except Exception as exc:
        failures.append(str(exc))
    status = "PASS" if not failures else "FAIL"
    authority = (policy or {}).get("authority", {})
    report = {
        "phase": "3.6b.3d.1",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tests_run": tests_run,
        "minimum_tests_required": MINIMUM_TESTS,
        "critical_failures": failures,
        "certification_result": {
            "sec_registrant_collection_authorized": authority.get("sec_registrant_collection") is True,
            "registrant_registry_build_authorized": authority.get("registrant_registry_build") is True,
            "issuer_identity_ledger_rebuild_authorized": authority.get("issuer_identity_ledger_rebuild") is True,
            "production_taxonomy_classification_authorized": authority.get("production_taxonomy_classification") is True,
            "relative_return_calculation_authorized": authority.get("relative_return_calculation") is True,
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 3.6b.3d.1 SEC registrant name enrichment certification: {status}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {REPORT}")
    for failure in failures:
        print(f"CRITICAL: {failure}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
