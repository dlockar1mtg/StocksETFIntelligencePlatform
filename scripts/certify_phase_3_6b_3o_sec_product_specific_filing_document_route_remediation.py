from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-t", str(root), "-p", "test_*.py"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    tests_run = 0
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            tests_run = int(line.split()[1])
    report = {
        "phase": "3.6b.3o",
        "status": "PASS" if result.returncode == 0 and tests_run >= 622 else "FAIL",
        "tests_run": tests_run,
        "minimum_tests_required": 622,
        "certification_result": {
            "route_remediation_review_authorized": True,
            "five_security_remediation_pilot_authorized": True,
            "remediated_route_reliability_certification_authorized": False,
            "full_priority_batch_recapture_authorized": False,
            "taxonomy_evidence_normalization_authorized": False,
            "production_taxonomy_classification_authorized": False,
        },
        "critical_failures": [] if result.returncode == 0 and tests_run >= 622 else ["REGRESSION_SUITE_FAILED_OR_FLOOR_NOT_MET"],
    }
    output = root / "artifacts" / "certification" / "phase_3_6b_3o_sec_product_specific_filing_document_route_remediation_certification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(combined, end="")
    print(f"Phase 3.6b.3o SEC product-specific filing document route remediation certification: {report['status']}")
    print(f"Tests executed: {tests_run}")
    print(f"Report: {output}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
