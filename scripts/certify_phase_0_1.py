import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "certification"
REPORT_PATH = ARTIFACT_DIR / "phase_0_1_certification.json"


def run_tests() -> tuple[int, str]:
    process = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = (process.stdout or "") + (process.stderr or "")
    return process.returncode, output


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return_code, output = run_tests()
    status = "PASS" if return_code == 0 else "FAIL"
    report = {
        "phase": "0.1",
        "certification": "governance_authority_package",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "critical_failures": [] if status == "PASS" else ["governance_regression_test_failure"],
        "authorized_uses": ["repository_scaffolding", "governance_validation", "research_only_development"],
        "unauthorized_uses": [
            "certified_market_monitoring",
            "certified_asset_outlook",
            "certified_portfolio_action",
            "certified_contribution_allocation",
            "certified_uip_export",
            "automatic_execution",
        ],
        "test_output": output,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output, end="")
    print(f"\nPhase 0.1 certification: {status}")
    print(f"Report: {REPORT_PATH}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
