from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 11)
REQUIRED_FILES = [
    "pyproject.toml",
    "config/governance/governance_manifest.json",
    "config/architecture/repository_layers.json",
]


def main() -> int:
    failures: list[str] = []
    if sys.version_info < MIN_PYTHON:
        failures.append(f"python_too_old:{platform.python_version()}")
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            failures.append(f"missing_required_file:{relative}")
    for relative in REQUIRED_FILES[1:]:
        try:
            json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))
        except Exception as exc:  # fail closed with precise evidence
            failures.append(f"invalid_json:{relative}:{exc}")

    print(f"Repository: {ROOT}")
    print(f"Python: {platform.python_version()}")
    print(f"Environment validation: {'PASS' if not failures else 'FAIL'}")
    for failure in failures:
        print(f"- {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
