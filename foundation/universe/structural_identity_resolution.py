from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "universe" / "structural_identity_resolution_policy.json"


class StructuralIdentityResolutionError(ValueError):
    """Raised when identity resolution violates governed requirements."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("phase") != "2" or policy.get("subphase") != "2A.4":
        raise StructuralIdentityResolutionError("Unexpected identity-resolution phase")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise StructuralIdentityResolutionError("Evidence-determined sizing is required")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise StructuralIdentityResolutionError("An arbitrary target universe size is prohibited")
    if policy.get("preserve_full_discovery_universe") is not True:
        raise StructuralIdentityResolutionError("The full discovery universe must be preserved")
    if policy.get("destructive_deletion_allowed") is not False or policy.get("fail_closed") is not True:
        raise StructuralIdentityResolutionError("Identity resolution must be non-destructive and fail closed")
    forbidden = (
        "production_data_certification", "analytics", "forecasting", "ranking", "recommendations",
        "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes",
    )
    authority = policy.get("authority", {})
    if any(authority.get(name) is not False for name in forbidden):
        raise StructuralIdentityResolutionError("Identity resolution improperly expands authority")
    return policy


def _text(record: dict[str, Any]) -> str:
    values = [
        record.get("symbol"), record.get("name"), record.get("fund_name"),
        record.get("simple_name"), record.get("description"), record.get("type"),
        record.get("instrument_type"), record.get("asset_type"), record.get("state"),
    ]
    return " ".join(str(value) for value in values if value not in (None, "")).lower()


def attribute_unmatched(record: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Assign a conservative reason and resolution state from available evidence."""
    text = _text(record)
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    evidence: list[str] = []

    if any(term in text for term in ("exchange traded note", " etn", "senior note", "debt security")):
        return "ETN_OR_DEBT_SECURITY", "ALTERNATE_STRUCTURE_CONFIRMED", ["name_or_description_debt_pattern"]
    if any(term in text for term in ("grantor trust", "statutory trust", "commodity trust", "bitcoin trust", "ether trust", "gold trust", "silver trust")):
        return "SPECIALIZED_TRUST", "SPECIALIZED", ["name_or_description_trust_pattern"]
    if any(term in text for term in ("closed-end", "closed end fund", "unit investment trust", "partnership")):
        return "NON_1940_ACT_STRUCTURE", "ALTERNATE_STRUCTURE_CONFIRMED", ["alternate_structure_pattern"]
    if any(term in text for term in ("liquidating", "liquidation", "delisted", "terminated", "closing")):
        return "DELISTED_OR_RENAMED", "BLOCKED", ["inactive_or_closing_pattern"]
    if record.get("identity_conflict") is True or record.get("conflict_state") in {"CONFLICTED", "QUARANTINED"}:
        return "IDENTITY_CONFLICT", "QUARANTINED", ["upstream_identity_conflict"]
    if re.search(r"[./-]", symbol):
        return "SYMBOL_NORMALIZATION_REQUIRED", "REQUIRES_ADDITIONAL_SOURCE", ["noncanonical_symbol_pattern"]
    if record.get("inception_date") in (None, "") and any(term in text for term in ("new", "recent", "launch", "pending")):
        return "RECENT_OR_PENDING_SEC_RECORD", "REQUIRES_ADDITIONAL_SOURCE", ["recent_or_pending_pattern"]
    issuer = record.get("issuer_name") or record.get("issuer")
    if issuer not in (None, ""):
        evidence.append("issuer_available")
        return "ISSUER_EVIDENCE_REQUIRED", "REQUIRES_ADDITIONAL_SOURCE", evidence
    return "UNRESOLVED", "UNRESOLVED", evidence


def resolve_identities(
    sec_reconciliation: dict[str, Any],
    universe_records: list[dict[str, Any]],
) -> dict[str, Any]:
    policy = load_policy()
    reconciliation_records = sec_reconciliation.get("records")
    if not isinstance(reconciliation_records, list):
        raise StructuralIdentityResolutionError("SEC reconciliation records are required")
    if len(reconciliation_records) != len(universe_records):
        raise StructuralIdentityResolutionError("Universe and SEC reconciliation counts must match")

    universe_by_id = {record.get("security_id"): record for record in universe_records}
    if None in universe_by_id or len(universe_by_id) != len(universe_records):
        raise StructuralIdentityResolutionError("Universe requires unique stable security identities")

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for sec_record in reconciliation_records:
        security_id = sec_record.get("security_id")
        if security_id in seen or security_id not in universe_by_id:
            raise StructuralIdentityResolutionError("SEC reconciliation identity mismatch or duplicate")
        seen.add(security_id)
        source = universe_by_id[security_id]
        state = sec_record.get("reconciliation_state")
        base = {
            "security_id": security_id,
            "symbol": sec_record.get("symbol") or source.get("symbol"),
            "analytics_authorized": False,
            "recommendations_authorized": False,
            "uip_export_authorized": False,
            "automatic_execution_authorized": False,
        }
        if state == "MATCHED":
            required = ("sec_cik", "sec_series_id", "sec_class_contract_id")
            if any(sec_record.get(field) in (None, "") for field in required):
                raise StructuralIdentityResolutionError("Matched SEC identity is incomplete")
            resolved = {
                **base,
                "resolution_state": policy["matched_state"],
                "attribution_reason": None,
                "sec_cik": sec_record["sec_cik"],
                "sec_series_id": sec_record["sec_series_id"],
                "sec_class_contract_id": sec_record["sec_class_contract_id"],
                "sec_fund_name": sec_record.get("sec_fund_name"),
                "evidence": ["SEC_COMPANY_TICKERS_MF_UNIQUE_MATCH"],
            }
            matched.append(resolved)
        elif state == "UNMATCHED":
            reason, resolution_state, evidence = attribute_unmatched(source)
            resolved = {
                **base,
                "resolution_state": resolution_state,
                "attribution_reason": reason,
                "sec_cik": None,
                "sec_series_id": None,
                "sec_class_contract_id": None,
                "sec_fund_name": None,
                "evidence": evidence,
            }
            unmatched.append(resolved)
        elif state == "CONFLICTED":
            resolved = {
                **base,
                "resolution_state": "QUARANTINED",
                "attribution_reason": "IDENTITY_CONFLICT",
                "sec_cik": None,
                "sec_series_id": None,
                "sec_class_contract_id": None,
                "sec_fund_name": None,
                "evidence": ["SEC_MULTIPLE_IDENTITY_CANDIDATES"],
            }
            unmatched.append(resolved)
        else:
            raise StructuralIdentityResolutionError(f"Unknown reconciliation state: {state}")
        all_records.append(resolved)

    if len(seen) != len(universe_records):
        raise StructuralIdentityResolutionError("Resolution did not preserve the full universe")

    state_counts = Counter(record["resolution_state"] for record in all_records)
    reason_counts = Counter(record["attribution_reason"] for record in unmatched)
    return {
        "total_records": len(all_records),
        "sec_identity_confirmed": len(matched),
        "unmatched_or_conflicted": len(unmatched),
        "resolution_state_counts": dict(sorted(state_counts.items())),
        "unmatched_reason_counts": dict(sorted(reason_counts.items())),
        "matched_records": matched,
        "unmatched_records": unmatched,
        "records": all_records,
        "selection_principle": "EVIDENCE_DETERMINES_SIZE",
        "target_universe_size": None,
        "full_discovery_universe_preserved": True,
        "destructive_deletion_allowed": False,
    }
