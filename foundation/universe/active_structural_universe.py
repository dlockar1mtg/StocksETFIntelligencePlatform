from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "universe" / "active_structural_universe_policy.json"


class ActiveStructuralUniverseError(ValueError):
    pass


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("phase") != "2" or policy.get("subphase") != "2A.5":
        raise ActiveStructuralUniverseError("Unexpected active-universe phase")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise ActiveStructuralUniverseError("Evidence-determined sizing is required")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise ActiveStructuralUniverseError("Arbitrary target size is prohibited")
    if policy.get("preserve_full_discovery_universe") is not True:
        raise ActiveStructuralUniverseError("Full discovery universe must be preserved")
    if policy.get("destructive_deletion_allowed") is not False or policy.get("fail_closed") is not True:
        raise ActiveStructuralUniverseError("Promotion must be non-destructive and fail closed")
    return policy


def promote_active_universe(snapshot: dict[str, Any]) -> dict[str, Any]:
    policy = load_policy()
    records = snapshot.get("records")
    if not isinstance(records, list) or not records:
        raise ActiveStructuralUniverseError("Identity-resolution records are required")
    ids = [record.get("security_id") for record in records]
    if None in ids or len(set(ids)) != len(ids):
        raise ActiveStructuralUniverseError("Stable security identities must be complete and unique")

    active: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for record in records:
        state = record.get("resolution_state")
        base = dict(record)
        base["analytics_authorized"] = False
        base["recommendations_authorized"] = False
        base["uip_export_authorized"] = False
        base["automatic_execution_authorized"] = False
        if state == policy["required_active_resolution_state"]:
            base["processing_state"] = "ACTIVE_STRUCTURAL_UNIVERSE"
            base["market_data_collection_authorized"] = True
            active.append(base)
        else:
            base["processing_state"] = policy["deferred_processing_state"]
            base["processing_reason"] = policy["deferred_reason"]
            base["market_data_collection_authorized"] = False
            deferred.append(base)

    active_symbols = {str(record.get("symbol") or "").upper() for record in active}
    missing = [symbol for symbol in policy["required_seed_symbols"] if symbol not in active_symbols]
    if missing:
        raise ActiveStructuralUniverseError(f"Required seed ETFs are not active: {missing}")

    if len(active) + len(deferred) != len(records):
        raise ActiveStructuralUniverseError("Active and deferred populations do not reconcile")

    return {
        "total_discovery_records": len(records),
        "active_structural_records": len(active),
        "deferred_research_only_records": len(deferred),
        "active_records": active,
        "deferred_records": deferred,
        "required_seed_symbols": policy["required_seed_symbols"],
        "selection_principle": policy["selection_principle"],
        "target_universe_size": None,
        "full_discovery_universe_preserved": True,
        "destructive_deletion_allowed": False,
    }
