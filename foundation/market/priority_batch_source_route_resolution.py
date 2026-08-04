from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class PriorityBatchRouteError(ValueError):
    pass


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise PriorityBatchRouteError("RECORD_ARRAY_MISSING")


def build_priority_batch_route_ledger(
    manifest_document: Any,
    sec_identity_document: Any,
    policy: dict[str, Any],
) -> dict[str, Any]:
    manifest = _records(manifest_document)
    sec_records = _records(sec_identity_document)
    required = int(policy["required_manifest_count"])
    if len(manifest) != required:
        raise PriorityBatchRouteError("MANIFEST_COUNT_MISMATCH")

    security_ids = [record.get("security_id") for record in manifest]
    if None in security_ids or len(set(security_ids)) != required:
        raise PriorityBatchRouteError("DUPLICATE_OR_MISSING_MANIFEST_IDENTITY")

    sec_by_id: dict[str, list[dict[str, Any]]] = {}
    for record in sec_records:
        security_id = record.get("security_id")
        if security_id:
            sec_by_id.setdefault(str(security_id), []).append(record)

    output: list[dict[str, Any]] = []
    for source in manifest:
        security_id = str(source["security_id"])
        symbol = source.get("symbol")
        base = {
            "security_id": security_id,
            "symbol": symbol,
            "issuer_key": source.get("issuer_key"),
            "route_state": "ROUTE_UNRESOLVED",
            "route_reasons": [],
            "sec_cik": None,
            "sec_series_id": None,
            "sec_class_contract_id": None,
            "candidate_routes": [],
            "selected_source_tier": None,
            "selected_source_url": None,
            "source_capture_authorized": False,
            "source_capture_executed": False,
            "taxonomy_dimensions_assigned": False,
            "taxonomy_classification_authorized": False,
            "production_taxonomy_authority": False,
        }

        if source.get("acquisition_state") != "PENDING":
            base["route_state"] = "ROUTE_QUARANTINED"
            base["route_reasons"].append("MANIFEST_RECORD_NOT_PENDING")
            output.append(base)
            continue

        matches = sec_by_id.get(security_id, [])
        if not matches:
            base["route_reasons"].append("SEC_IDENTITY_RECORD_MISSING")
            output.append(base)
            continue
        if len(matches) > 1:
            base["route_state"] = "ROUTE_CONFLICTED"
            base["route_reasons"].append("MULTIPLE_SEC_IDENTITY_RECORDS")
            output.append(base)
            continue

        sec = matches[0]
        state = sec.get("resolution_state") or sec.get("identity_state") or sec.get("status")
        if state not in {"SEC_IDENTITY_CONFIRMED", "MATCHED", "CONFIRMED", "ACTIVE"}:
            base["route_reasons"].append("SEC_IDENTITY_NOT_CONFIRMED")
            output.append(base)
            continue

        cik = sec.get("sec_cik") or sec.get("cik")
        series_id = sec.get("sec_series_id") or sec.get("series_id")
        class_id = sec.get("sec_class_contract_id") or sec.get("class_contract_id") or sec.get("class_id")
        if not cik or not series_id or not class_id:
            base["route_state"] = "ROUTE_QUARANTINED"
            base["route_reasons"].append("SEC_SERIES_CLASS_IDENTITY_INCOMPLETE")
            output.append(base)
            continue

        normalized_cik = str(cik).strip().zfill(10)
        base.update(
            {
                "route_state": "ROUTE_CANDIDATE_READY",
                "route_reasons": ["SEC_SERIES_CLASS_IDENTITY_CONFIRMED"],
                "sec_cik": normalized_cik,
                "sec_series_id": str(series_id).strip(),
                "sec_class_contract_id": str(class_id).strip(),
                "candidate_routes": [
                    {
                        "source_tier": "SEC_FILING",
                        "official_domain": "sec.gov",
                        "route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY",
                        "identity_markers": {
                            "cik": normalized_cik,
                            "series_id": str(series_id).strip(),
                            "class_contract_id": str(class_id).strip(),
                        },
                        "route_resolution_required": True,
                        "capture_authorized": False,
                    },
                    {
                        "source_tier": "ISSUER_PRODUCT_PAGE",
                        "official_domain": "ishares.com",
                        "route_type": "ISHARES_SYMBOL_PRODUCT_DISCOVERY",
                        "identity_markers": {
                            "symbol": symbol,
                            "class_contract_id": str(class_id).strip(),
                        },
                        "route_resolution_required": True,
                        "capture_authorized": False,
                    },
                ],
            }
        )
        output.append(base)

    counts = Counter(record["route_state"] for record in output)
    ready = counts.get("ROUTE_CANDIDATE_READY", 0) + counts.get("ROUTE_RESOLVED", 0)
    return {
        "phase": "3.6b.3g",
        "selected_priority_rank": int(policy["selected_priority_rank"]),
        "selected_issuer_key": policy["selected_issuer_key"],
        "selected_issuer_name": policy["selected_issuer_name"],
        "required_manifest_count": required,
        "record_count": len(output),
        "route_state_counts": dict(sorted(counts.items())),
        "route_candidate_ready_count": ready,
        "route_blocked_count": required - ready,
        "route_coverage_complete": ready == required,
        "source_capture_executed": False,
        "next_required_step": (
            "PRIORITY_BATCH_ROUTE_DISCOVERY_PILOT"
            if ready == required
            else "PRIORITY_BATCH_ROUTE_REMEDIATION"
        ),
        "records": output,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {key: value for key, value in result.items() if key != "records"}
    compact["route_ledger_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
