from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from foundation.market.priority_batch_controlled_source_capture_execution import (
    build_summary,
    execute_capture,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-plan", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()

    plan_bytes = args.capture_plan.read_bytes()
    plan = json.loads(plan_bytes.decode("utf-8"))
    authorization_bytes = args.authorization.read_bytes()
    authorization = json.loads(authorization_bytes.decode("utf-8"))
    policy = _load(args.policy)

    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    if plan_hash != policy["required_capture_plan_sha256"]:
        raise ValueError("Capture-plan SHA-256 does not match policy")
    authorization_hash = hashlib.sha256(authorization_bytes).hexdigest()
    if authorization_hash != policy["required_authorization_sha256"]:
        raise ValueError("Authorization SHA-256 does not match policy")

    result = execute_capture(
        plan=plan,
        authorization=authorization,
        policy=policy,
        output_path=args.output,
        user_agent=args.user_agent,
    )
    summary = build_summary(result, args.output)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
