from __future__ import annotations

import hashlib
import urllib.request
from datetime import datetime, timezone
from typing import Any


class PilotTaxonomyError(ValueError):
    """Raised when pilot evidence fails closed."""


def _valid_hash(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def fetch_source(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "StocksETFIntelligencePlatform/3.6b.3b devon.lockard@example.com",
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def content_supports_entry(content: bytes, entry: dict[str, Any]) -> bool:
    text = content.decode("utf-8", errors="ignore").lower()
    return all(str(term).lower() in text for term in entry["required_content_terms"])


def normalize_pilot_record(
    manifest_record: dict[str, Any],
    registry_entry: dict[str, Any],
    policy: dict[str, Any],
    source_content: bytes | None = None,
) -> dict[str, Any]:
    security_id = manifest_record.get("security_id")
    if security_id not in set(policy["required_security_ids"]):
        raise PilotTaxonomyError("PILOT_SECURITY_ID_NOT_AUTHORIZED")
    if str(manifest_record.get("symbol", "")).upper() != str(registry_entry.get("symbol", "")).upper():
        raise PilotTaxonomyError("PILOT_SYMBOL_MISMATCH")

    result = {
        "security_id": security_id,
        "symbol": registry_entry["symbol"],
        "issuer_key": registry_entry["issuer_key"],
        "classification_status": "UNRESOLVED",
        "classification_reasons": [],
        "source_tier": registry_entry["source_tier"],
        "source_url": registry_entry["source_url"],
        "source_record_id": registry_entry["source_record_id"],
        "content_sha256": None,
        "classified_at_utc": None,
        "taxonomy_classification_authorized": False,
        "production_taxonomy_authority": False,
    }

    content_hash = manifest_record.get("source_content_sha256")
    if manifest_record.get("acquisition_state") == "AUTHORITY_CAPTURED":
        if not _valid_hash(content_hash):
            result["classification_status"] = "QUARANTINED"
            result["classification_reasons"].append("CAPTURED_CONTENT_HASH_INVALID")
            return result
        result["content_sha256"] = content_hash
    elif source_content is not None:
        content_hash = hashlib.sha256(source_content).hexdigest()
        result["content_sha256"] = content_hash
    else:
        result["classification_reasons"].append("AUTHORITATIVE_CONTENT_UNAVAILABLE")
        return result

    if source_content is not None and not content_supports_entry(source_content, registry_entry):
        result["classification_status"] = "QUARANTINED"
        result["classification_reasons"].append("SOURCE_CONTENT_TERMS_MISSING")
        return result

    missing = [field for field in policy["required_dimensions"] if not registry_entry.get(field)]
    if missing:
        result["classification_status"] = "QUARANTINED"
        result["classification_reasons"].append("REQUIRED_DIMENSIONS_MISSING")
        result["classification_reasons"].extend(f"MISSING_{field.upper()}" for field in missing)
        return result

    for field in policy["required_dimensions"]:
        result[field] = registry_entry[field]
    result["classification_status"] = "CLASSIFIED"
    result["classified_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["taxonomy_classification_authorized"] = True
    return result


def summarize(records: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        state = record["classification_status"]
        counts[state] = counts.get(state, 0) + 1
    complete = len(records) == int(policy["required_record_count"]) and counts.get("CLASSIFIED", 0) == int(policy["required_record_count"])
    return {
        "phase": "3.6b.3b",
        "record_count": len(records),
        "classification_state_counts": dict(sorted(counts.items())),
        "pilot_taxonomy_complete": complete,
        "production_taxonomy_certified": False,
        "next_required_step": "ISSUER_BATCH_EXPANSION" if complete else "PILOT_SOURCE_REMEDIATION",
        "authority": policy["authority"],
    }
