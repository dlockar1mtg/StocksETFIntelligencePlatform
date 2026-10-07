from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class IssuerLedgerRebuildError(ValueError):
    pass


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise IssuerLedgerRebuildError("RECORD_ARRAY_MISSING")


def _normalize_cik(value: Any) -> str | None:
    if value in (None, ""):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


def build_issuer_identity_ledger(
    batch_plan_document: Any,
    sec_identity_document: Any,
    registrant_registry_document: Any,
    pilot_taxonomy_document: Any,
    policy: dict[str, Any],
) -> dict[str, Any]:
    plan = _records(batch_plan_document)
    sec_records = _records(sec_identity_document)
    registrants = _records(registrant_registry_document)
    pilot_records = _records(pilot_taxonomy_document)
    required = int(policy["required_full_population"])

    if len(plan) != required:
        raise IssuerLedgerRebuildError("FULL_POPULATION_COUNT_MISMATCH")
    plan_ids = [record.get("security_id") for record in plan]
    if None in plan_ids or len(set(plan_ids)) != required:
        raise IssuerLedgerRebuildError("DUPLICATE_OR_MISSING_PLAN_IDENTITY")

    sec_by_id: dict[str, list[dict[str, Any]]] = {}
    for record in sec_records:
        security_id = record.get("security_id")
        if security_id:
            sec_by_id.setdefault(str(security_id), []).append(record)

    registrant_by_cik: dict[str, list[dict[str, Any]]] = {}
    for record in registrants:
        cik = _normalize_cik(record.get("cik"))
        if cik:
            registrant_by_cik.setdefault(cik, []).append(record)

    pilot_by_id = {
        str(record.get("security_id")): record
        for record in pilot_records
        if record.get("security_id")
    }

    output: list[dict[str, Any]] = []
    for plan_record in plan:
        security_id = str(plan_record["security_id"])
        base = {
            "security_id": security_id,
            "symbol": plan_record.get("symbol"),
            "issuer_identity_state": "ISSUER_UNRESOLVED",
            "issuer_key": None,
            "issuer_name": None,
            "issuer_cik": None,
            "issuer_entity_role": None,
            "source_tier": None,
            "source_record_id": None,
            "source_payload_sha256": None,
            "source_retrieved_at_utc": None,
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
                "issuer_entity_role": "PILOT_EVIDENCE_BACKED_ISSUER",
                "source_tier": pilot.get("source_tier"),
                "source_record_id": pilot.get("source_record_id"),
                "source_payload_sha256": pilot.get("content_sha256"),
            })
            output.append(base)
            continue

        sec_matches = sec_by_id.get(security_id, [])
        if not sec_matches:
            base["issuer_identity_reasons"].append("SEC_IDENTITY_RECORD_MISSING")
            output.append(base)
            continue
        if len(sec_matches) > 1:
            base["issuer_identity_state"] = "ISSUER_CONFLICTED"
            base["issuer_identity_reasons"].append("MULTIPLE_SEC_IDENTITY_RECORDS")
            output.append(base)
            continue

        sec = sec_matches[0]
        if sec.get("resolution_state") not in {"SEC_IDENTITY_CONFIRMED", "MATCHED", "CONFIRMED", "ACTIVE"}:
            base["issuer_identity_reasons"].append("SEC_IDENTITY_NOT_CONFIRMED")
            output.append(base)
            continue

        cik = _normalize_cik(sec.get("sec_cik"))
        if not cik:
            base["issuer_identity_state"] = "ISSUER_QUARANTINED"
            base["issuer_identity_reasons"].append("SEC_CIK_MISSING_OR_INVALID")
            output.append(base)
            continue

        registry_matches = registrant_by_cik.get(cik, [])
        if not registry_matches:
            base["issuer_identity_reasons"].append("REGISTRANT_REGISTRY_RECORD_MISSING")
            base["issuer_cik"] = cik
            output.append(base)
            continue
        if len(registry_matches) > 1:
            base["issuer_identity_state"] = "ISSUER_CONFLICTED"
            base["issuer_cik"] = cik
            base["issuer_identity_reasons"].append("MULTIPLE_REGISTRANT_REGISTRY_RECORDS")
            output.append(base)
            continue

        registrant = registry_matches[0]
        if registrant.get("state") != policy["required_registrant_state"]:
            base["issuer_cik"] = cik
            base["issuer_identity_reasons"].append("REGISTRANT_NOT_CONFIRMED")
            output.append(base)
            continue

        name = str(registrant.get("registrant_name") or "").strip()
        payload_hash = str(registrant.get("payload_sha256") or "").strip().lower()
        if not name or len(payload_hash) != 64 or any(character not in "0123456789abcdef" for character in payload_hash):
            base["issuer_identity_state"] = "ISSUER_QUARANTINED"
            base["issuer_cik"] = cik
            base["issuer_identity_reasons"].append("REGISTRANT_LINEAGE_INCOMPLETE")
            output.append(base)
            continue

        base.update({
            "issuer_identity_state": "ISSUER_CONFIRMED",
            "issuer_key": f"SEC-CIK-{cik}",
            "issuer_name": name,
            "issuer_cik": cik,
            "issuer_entity_role": "SEC_REGISTRANT_LEGAL_ENTITY",
            "source_tier": "SEC_SUBMISSIONS_API",
            "source_record_id": f"SEC-SUBMISSIONS-{cik}",
            "source_payload_sha256": payload_hash,
            "source_retrieved_at_utc": registrant.get("retrieved_at_utc"),
        })
        output.append(base)

    counts = Counter(record["issuer_identity_state"] for record in output)
    confirmed = counts.get("ISSUER_CONFIRMED", 0) + counts.get("PILOT_COMPLETE", 0)
    result = {
        "phase": "3.6b.3d.2",
        "required_record_count": required,
        "record_count": len(output),
        "issuer_identity_state_counts": dict(sorted(counts.items())),
        "issuer_confirmed_count": confirmed,
        "issuer_unresolved_count": required - confirmed,
        "issuer_identity_coverage_complete": confirmed == required,
        "next_required_step": "ISSUER_BATCH_PLAN_REBUILD" if confirmed == required else "ISSUER_IDENTITY_REMEDIATION",
        "records": output,
        "authority": policy["authority"],
    }
    return result


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {key: value for key, value in result.items() if key != "records"}
    compact["issuer_identity_ledger_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
