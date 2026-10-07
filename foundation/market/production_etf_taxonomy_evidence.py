from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


class TaxonomyEvidenceError(ValueError):
    """Raised when Phase 3.6b.1 evidence fails closed."""


def build_url(symbol: str, policy: dict[str, Any]) -> str:
    if not symbol or not symbol.replace("-", "").replace(".", "").isalnum():
        raise TaxonomyEvidenceError("INVALID_SYMBOL")
    return policy["source"]["endpoint_template"].format(symbol=urllib.parse.quote(symbol))


def fetch_payload(symbol: str, policy: dict[str, Any], timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        build_url(symbol, policy),
        headers={"User-Agent": "StocksETFIntelligencePlatform/3.6b.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def normalize_payload(
    security_id: str,
    symbol: str,
    payload: bytes,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    if not security_id:
        raise TaxonomyEvidenceError("MISSING_SECURITY_ID")
    retrieved = retrieved_at_utc or datetime.now(timezone.utc).isoformat()
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    try:
        document = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise TaxonomyEvidenceError("MALFORMED_PROVIDER_PAYLOAD") from exc

    quotes = document.get("quotes") if isinstance(document, dict) else None
    quotes = quotes if isinstance(quotes, list) else []
    exact = [item for item in quotes if str(item.get("symbol", "")).upper() == symbol.upper()]
    if not exact:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "collection_state": "NOT_FOUND" if not quotes else "SYMBOL_MISMATCH",
            "provider_symbol": None,
            "quote_type": None,
            "short_name": None,
            "long_name": None,
            "exchange": None,
            "provider_payload_sha256": payload_sha256,
            "retrieved_at_utc": retrieved,
            "taxonomy_classification_authorized": False,
        }

    item = exact[0]
    return {
        "security_id": security_id,
        "symbol": symbol,
        "collection_state": "COLLECTED",
        "provider_symbol": item.get("symbol"),
        "quote_type": item.get("quoteType"),
        "short_name": item.get("shortname"),
        "long_name": item.get("longname"),
        "exchange": item.get("exchange"),
        "provider_payload_sha256": payload_sha256,
        "retrieved_at_utc": retrieved,
        "taxonomy_classification_authorized": False,
    }


def provider_error_record(security_id: str, symbol: str, error: Exception) -> dict[str, Any]:
    return {
        "security_id": security_id,
        "symbol": symbol,
        "collection_state": "PROVIDER_ERROR",
        "provider_symbol": None,
        "quote_type": None,
        "short_name": None,
        "long_name": None,
        "exchange": None,
        "provider_payload_sha256": None,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "error_type": type(error).__name__,
        "error_message": str(error),
        "taxonomy_classification_authorized": False,
    }
