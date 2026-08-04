from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ETFTaxonomyError(ValueError):
    pass


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ETFTaxonomyError("Invalid classification timestamp") from exc
    if parsed.tzinfo is None:
        raise ETFTaxonomyError("Classification timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def validate_taxonomy_record(record: dict[str, Any], policy: dict[str, Any], as_of_utc: datetime) -> str:
    required = {
        "security_id", "asset_class", "strategy", "geography", "market_segment",
        "income_profile", "implementation", "specialized_product_type",
        "portfolio_treatment", "classification_status", "classified_at_utc",
        "source_id", "source_record_id", "content_sha256",
    }
    missing = required - set(record)
    if missing:
        raise ETFTaxonomyError(f"Missing taxonomy fields: {sorted(missing)}")
    if not str(record["security_id"]).startswith("SEC-US-"):
        raise ETFTaxonomyError("Stable security identity is required")
    if record["asset_class"] not in policy["asset_classes"]:
        raise ETFTaxonomyError("Unknown asset class")
    if record["strategy"] not in policy["strategy_types"]:
        raise ETFTaxonomyError("Unknown strategy")
    if record["specialized_product_type"] not in policy["specialized_product_types"]:
        raise ETFTaxonomyError("Unknown specialized product type")
    if record["portfolio_treatment"] not in policy["portfolio_treatments"]:
        raise ETFTaxonomyError("Unknown portfolio treatment")
    if record["classification_status"] != "CLASSIFIED":
        return "QUARANTINED"
    classified_at = _parse_utc(record["classified_at_utc"])
    if classified_at > as_of_utc.astimezone(timezone.utc):
        raise ETFTaxonomyError("Future classification evidence is not allowed")
    digest = str(record["content_sha256"])
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ETFTaxonomyError("Invalid taxonomy evidence digest")
    specialized = record["specialized_product_type"] != "NONE"
    if specialized and record["portfolio_treatment"] == "STANDARD_CANDIDATE":
        raise ETFTaxonomyError("Specialized products cannot default to standard treatment")
    if specialized and record["specialized_product_type"] not in policy["specialized_review_required_for"]:
        raise ETFTaxonomyError("Specialized review policy is incomplete")
    return record["portfolio_treatment"]


def validate_taxonomy_snapshot(records: list[dict[str, Any]], policy: dict[str, Any], as_of_utc: datetime) -> list[str]:
    seen: set[str] = set()
    treatments: list[str] = []
    for record in records:
        security_id = record.get("security_id")
        if security_id in seen:
            raise ETFTaxonomyError("Duplicate security taxonomy record")
        seen.add(security_id)
        treatments.append(validate_taxonomy_record(record, policy, as_of_utc))
    return treatments
