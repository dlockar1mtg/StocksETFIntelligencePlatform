from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "universe" / "robinhood_snapshot_policy.json"


def load_policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def validate_snapshot(snapshot: dict[str, Any]) -> list[str]:
    policy = load_policy()
    errors: list[str] = []

    required_top = {
        "snapshot_id", "operating_date", "operating_timezone", "generated_at_utc",
        "broker_id", "snapshot_status", "lineage", "counts", "records",
    }
    missing_top = sorted(required_top - set(snapshot))
    if missing_top:
        errors.append(f"missing top-level fields: {missing_top}")
        return errors

    if snapshot["operating_timezone"] != policy["operating_timezone"]:
        errors.append("operating timezone mismatch")
    if snapshot["broker_id"] != policy["broker_id"]:
        errors.append("broker mismatch")

    records = snapshot.get("records", [])
    security_ids = [record.get("security_id") for record in records]
    if len(security_ids) != len(set(security_ids)):
        errors.append("duplicate security_id in snapshot")

    required_seeds = set(policy["seed_security_ids"])
    if not required_seeds.issubset(set(security_ids)):
        errors.append("required seed securities missing")

    allowed = {
        "discovery_status": set(policy["allowed_discovery_states"]),
        "broker_status": set(policy["allowed_broker_states"]),
        "taxonomy_status": set(policy["allowed_taxonomy_states"]),
        "analytics_status": set(policy["allowed_analytics_states"]),
        "final_state": set(policy["allowed_final_states"]),
    }

    for record in records:
        for field, values in allowed.items():
            if record.get(field) not in values:
                errors.append(f"{record.get('security_id')}: invalid {field}")
        if not record.get("reason_codes"):
            errors.append(f"{record.get('security_id')}: reason_codes required")
        if record.get("broker_status") == "UNKNOWN" and record.get("final_state") in {
            "BROKER_ELIGIBLE", "ANALYTICS_PROVISIONAL", "ANALYTICS_ELIGIBLE", "SPECIALIZED"
        }:
            errors.append(f"{record.get('security_id')}: unknown broker status promoted")
        if record.get("taxonomy_status") == "PENDING" and record.get("final_state") in {
            "ANALYTICS_PROVISIONAL", "ANALYTICS_ELIGIBLE", "SPECIALIZED"
        }:
            errors.append(f"{record.get('security_id')}: pending taxonomy promoted")
        if record.get("analytics_status") == "BLOCKED" and record.get("final_state") in {
            "ANALYTICS_PROVISIONAL", "ANALYTICS_ELIGIBLE", "SPECIALIZED"
        }:
            errors.append(f"{record.get('security_id')}: blocked analytics promoted")
        if record.get("evidence_state") == "PENDING" and not any(
            "PENDING" in code for code in record.get("reason_codes", [])
        ):
            errors.append(f"{record.get('security_id')}: pending evidence not explicit")

    counts = snapshot.get("counts", {})
    final_counts = Counter(record.get("final_state") for record in records)
    expected_counts = {
        "total_records": len(records),
        "discovered": sum(record.get("discovery_status") == "DISCOVERED" for record in records),
        "broker_eligible": final_counts["BROKER_ELIGIBLE"],
        "analytics_provisional": final_counts["ANALYTICS_PROVISIONAL"],
        "analytics_eligible": final_counts["ANALYTICS_ELIGIBLE"],
        "blocked": final_counts["BLOCKED"],
        "quarantined": final_counts["QUARANTINED"],
        "excluded": final_counts["EXCLUDED"],
    }
    if counts != expected_counts:
        errors.append("snapshot counts do not reconcile")

    lineage = snapshot.get("lineage", {})
    sha = lineage.get("source_bundle_sha256", "")
    if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
        errors.append("invalid source bundle sha256")

    return errors
