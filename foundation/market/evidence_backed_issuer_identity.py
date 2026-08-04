from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class IssuerIdentityError(ValueError):
    pass


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise IssuerIdentityError("RECORD_ARRAY_MISSING")


def _first(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def build_issuer_identity_ledger(
    batch_plan_document: Any,
    sec_identity_document: Any,
    pilot_taxonomy_document: Any,
    policy: dict[str, Any],
) -> dict[str, Any]:
    plan = _records(batch_plan_document)
    sec_records = _records(sec_identity_document)
    pilot_records = _records(pilot_taxonomy_document)
    required = int(policy["required_full_population"])
    if len(plan) != required:
        raise IssuerIdentityError("FULL_POPULATION_COUNT_MISMATCH")
    plan_ids = [record.get("security_id") for record in plan]
    if None in plan_ids or len(set(plan_ids)) != required:
        raise IssuerIdentityError("DUPLICATE_OR_MISSING_PLAN_IDENTITY")

    sec_by_id: dict[str, list[dict[str, Any]]] = {}
    for record in sec_records:
        security_id = record.get("security_id")
        if security_id:
            sec_by_id.setdefault(security_id, []).append(record)
    pilot_by_id = {record.get("security_id"): record for record in pilot_records}

    output: list[dict[str, Any]] = []
    for record in plan:
        security_id = record["security_id"]
        symbol = record.get("symbol")
        base = {
            "security_id": security_id,
            "symbol": symbol,
            "issuer_identity_state": "ISSUER_UNRESOLVED",
            "issuer_key": None,
            "issuer_name": None,
            "issuer_cik": None,
            "source_tier": None,
            "source_record_id": None,
            "issuer_identity_reasons": [],
            "taxonomy_dimensions_assigned": False,
            "production_taxonomy_authority": False,
        }
        pilot = pilot_by_id.get(security_id)
        if pilot and pilot.get("classification_status") == "CLASSIFIED":
            base.update({
                "issuer_identity_state": "PILOT_COMPLETE",
                "issuer_key": pilot.get("issuer_key"),
                "issuer_name": pilot.get("issuer_key"),
                "source_tier": pilot.get("source_tier"),
                "source_record_id": pilot.get("source_record_id"),
            })
            output.append(base)
            continue

        matches = sec_by_id.get(security_id, [])
        if not matches:
            base["issuer_identity_reasons"].append("SEC_IDENTITY_RECORD_MISSING")
            output.append(base)
            continue
        if len(matches) > 1:
            base["issuer_identity_state"] = "ISSUER_CONFLICTED"
            base["issuer_identity_reasons"].append("MULTIPLE_SEC_IDENTITY_RECORDS")
            output.append(base)
            continue
        sec = matches[0]
        status = _first(sec, ("resolution_state", "identity_state", "status", "classification_status"))
        if status not in {"SEC_IDENTITY_CONFIRMED", "MATCHED", "CONFIRMED", "ACTIVE"}:
            base["issuer_identity_reasons"].append("SEC_IDENTITY_NOT_CONFIRMED")
            output.append(base)
            continue
        issuer_name = _first(sec, ("registrant_name", "company_name", "entity_name", "issuer_name", "sec_company_name"))
        issuer_cik = _first(sec, ("registrant_cik", "cik", "issuer_cik", "sec_cik"))
        if not issuer_name or issuer_cik in (None, ""):
            base["issuer_identity_state"] = "ISSUER_QUARANTINED"
            base["issuer_identity_reasons"].append("SEC_ISSUER_FIELDS_INCOMPLETE")
            output.append(base)
            continue
        normalized_cik = str(issuer_cik).strip().lstrip("0") or "0"
        base.update({
            "issuer_identity_state": "ISSUER_CONFIRMED",
            "issuer_key": f"SEC-CIK-{normalized_cik.zfill(10)}",
            "issuer_name": str(issuer_name).strip(),
            "issuer_cik": normalized_cik.zfill(10),
            "source_tier": "SEC_REGISTRANT_IDENTITY",
            "source_record_id": _first(sec, ("source_record_id", "sec_record_id", "series_id", "class_id")) or security_id,
        })
        output.append(base)

    counts = Counter(record["issuer_identity_state"] for record in output)
    confirmed = counts.get("ISSUER_CONFIRMED", 0) + counts.get("PILOT_COMPLETE", 0)
    return {
        "phase": "3.6b.3d",
        "required_record_count": required,
        "record_count": len(output),
        "issuer_identity_state_counts": dict(sorted(counts.items())),
        "issuer_confirmed_count": confirmed,
        "issuer_unresolved_count": required - confirmed,
        "issuer_identity_coverage_complete": confirmed == required,
        "next_required_step": "ISSUER_BATCH_REBUILD" if confirmed == required else "ISSUER_IDENTITY_REMEDIATION",
        "records": output,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {key: value for key, value in result.items() if key != "records"}
    compact["issuer_identity_ledger_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
