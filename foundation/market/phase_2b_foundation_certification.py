from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "phase_2b_foundation_certification_policy.json"


class Phase2BFoundationCertificationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("subphase") != "2B.5" or policy.get("fail_closed") is not True:
        raise Phase2BFoundationCertificationError("Unexpected or non-fail-closed policy")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise Phase2BFoundationCertificationError("Evidence-determined sizing is required")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise Phase2BFoundationCertificationError("Arbitrary target sizes are prohibited")
    if policy.get("provisional_records_preserved") is not True:
        raise Phase2BFoundationCertificationError("Provisional records must be preserved")
    if policy.get("provisional_records_advance_to_phase_3") is not False:
        raise Phase2BFoundationCertificationError("Provisional records cannot advance to Phase 3")
    if policy.get("destructive_deletion_allowed") is not False:
        raise Phase2BFoundationCertificationError("Destructive deletion is prohibited")
    forbidden = ("full_history_collection", "analytics", "forecasting", "ranking", "recommendations", "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes")
    authority = policy.get("authority", {})
    if any(authority.get(key) is not False for key in forbidden):
        raise Phase2BFoundationCertificationError("Downstream authority expanded")
    return policy


def certify_and_publish(eligibility_path: Path, summary_path: Path, output_dir: Path) -> dict[str, Any]:
    policy = load_policy()
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = list(eligibility.get("records") or [])

    if len(records) != policy["required_total_records"]:
        raise Phase2BFoundationCertificationError("Eligibility record count drift")
    security_ids = [str(record.get("security_id") or "") for record in records]
    if any(not value for value in security_ids) or len(set(security_ids)) != len(records):
        raise Phase2BFoundationCertificationError("Stable security identities are missing or duplicated")

    state_counts = Counter(str(record.get("screen_state")) for record in records)
    expected_states = policy["required_state_counts"]
    for state, count in expected_states.items():
        if state_counts.get(state, 0) != count:
            raise Phase2BFoundationCertificationError(f"State count drift: {state}")

    reason_counts: Counter[str] = Counter()
    for record in records:
        for reason in record.get("screen_reasons") or []:
            reason_counts[str(reason)] += 1
    for reason, count in policy["required_reason_counts"].items():
        if reason_counts.get(reason, 0) != count:
            raise Phase2BFoundationCertificationError(f"Reason count drift: {reason}")

    if summary.get("screen_state_counts") != dict(sorted(state_counts.items())):
        raise Phase2BFoundationCertificationError("Summary state counts do not reconcile")

    candidates = [record for record in records if record.get("screen_state") in policy["phase_3_candidate_states"]]
    if len(candidates) != policy["phase_3_candidate_record_count"]:
        raise Phase2BFoundationCertificationError("Phase 3 candidate count drift")

    candidate_symbols = {str(record.get("symbol")) for record in candidates}
    for seed in policy["required_seed_symbols"]:
        if seed not in candidate_symbols:
            raise Phase2BFoundationCertificationError(f"Required seed missing from Phase 3 candidates: {seed}")

    if any(record.get("screen_state") == "MARKET_DATA_PROVISIONAL" for record in candidates):
        raise Phase2BFoundationCertificationError("Provisional record advanced to Phase 3")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / "phase_3_market_data_candidate_universe.json"
    attestation_path = output_dir / "phase_2b_foundation_attestation.json"
    candidate_document = {
        "phase": "3_CANDIDATE_INPUT",
        "operating_date": policy["operating_date"],
        "record_count": len(candidates),
        "admission_state": "MARKET_DATA_ELIGIBLE",
        "provisional_records_included": False,
        "analytics_authorized": False,
        "forecasting_authorized": False,
        "records": candidates,
    }
    candidate_path.write_text(json.dumps(candidate_document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    attestation = {
        "phase": "2B.5",
        "certification_status": "PASS",
        "operating_date": policy["operating_date"],
        "total_evidence_records": len(records),
        "phase_3_candidate_records": len(candidates),
        "provisional_records_preserved": state_counts.get("MARKET_DATA_PROVISIONAL", 0),
        "provisional_records_advance_to_phase_3": False,
        "state_counts": dict(sorted(state_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "eligibility_sha256": _sha256(eligibility_path),
        "eligibility_summary_sha256": _sha256(summary_path),
        "phase_3_candidate_sha256": _sha256(candidate_path),
        "selection_principle": policy["selection_principle"],
        "target_universe_size": None,
        "authority": policy["authority"],
    }
    attestation_path.write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"attestation": attestation, "candidate_path": str(candidate_path), "attestation_path": str(attestation_path)}
