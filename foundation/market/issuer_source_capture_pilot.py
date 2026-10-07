from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class IssuerSourceCaptureError(ValueError):
    """Raised when the Phase 3.6b.3a pilot fails closed."""


def _hostname_matches_official_domain(hostname: str | None, official_domain: str) -> bool:
    """Allow the official apex domain and its subdomains, but not lookalike domains."""
    if not hostname or not official_domain:
        return False
    host = hostname.rstrip(".").lower()
    domain = official_domain.rstrip(".").lower()
    return host == domain or host.endswith(f".{domain}")


def validate_registry_entry(security_id: str, entry: dict[str, Any], policy: dict[str, Any]) -> None:
    if not security_id:
        raise IssuerSourceCaptureError("STABLE_SECURITY_ID_MISSING")
    if entry.get("source_tier") not in set(policy["allowed_source_tiers"]):
        raise IssuerSourceCaptureError("SOURCE_TIER_NOT_ALLOWED")
    url = entry.get("source_url")
    domain = entry.get("official_domain")
    if not url or not domain:
        raise IssuerSourceCaptureError("SOURCE_IDENTITY_MISSING")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or not _hostname_matches_official_domain(parsed.hostname, domain):
        raise IssuerSourceCaptureError("UNOFFICIAL_ISSUER_DOMAIN")
    if not entry.get("issuer_key") or not entry.get("symbol"):
        raise IssuerSourceCaptureError("ISSUER_OR_SYMBOL_MISSING")


def fetch_source(entry: dict[str, Any], timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        entry["source_url"],
        headers={
            "User-Agent": "StocksETFIntelligencePlatform/3.6b.3a",
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def capture_record(
    security_id: str,
    entry: dict[str, Any],
    policy: dict[str, Any],
    raw_content: bytes,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    validate_registry_entry(security_id, entry, policy)
    retrieved = retrieved_at_utc or datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(raw_content).hexdigest()
    text = raw_content.decode("utf-8", errors="ignore").upper()
    symbol = str(entry["symbol"]).upper()
    issuer = str(entry["issuer_key"]).replace("_", " ").upper()
    reasons: list[str] = []
    state = "AUTHORITY_CAPTURED"
    if symbol not in text:
        state = "QUARANTINED"
        reasons.append("SYMBOL_NOT_PRESENT_IN_SOURCE")
    if issuer.split()[0] not in text:
        state = "QUARANTINED"
        reasons.append("ISSUER_NOT_PRESENT_IN_SOURCE")
    return {
        "security_id": security_id,
        "symbol": entry["symbol"],
        "issuer_key": entry["issuer_key"],
        "acquisition_state": state,
        "acquisition_reasons": reasons,
        "source_tier": entry["source_tier"],
        "source_url": entry["source_url"],
        "official_domain": entry["official_domain"],
        "source_content_sha256": content_hash,
        "retrieved_at_utc": retrieved,
        "taxonomy_dimensions_assigned": False,
        "taxonomy_classification_authorized": False,
    }


def failure_record(security_id: str, entry: dict[str, Any], error: Exception) -> dict[str, Any]:
    return {
        "security_id": security_id,
        "symbol": entry.get("symbol"),
        "issuer_key": entry.get("issuer_key"),
        "acquisition_state": "UNRESOLVED",
        "acquisition_reasons": ["SOURCE_CAPTURE_FAILED"],
        "source_tier": entry.get("source_tier"),
        "source_url": entry.get("source_url"),
        "official_domain": entry.get("official_domain"),
        "source_content_sha256": None,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "error_type": type(error).__name__,
        "error_message": str(error),
        "taxonomy_dimensions_assigned": False,
        "taxonomy_classification_authorized": False,
    }


def write_raw_content(directory: Path, symbol: str, content: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{symbol.lower()}_issuer_source.bin"
    path.write_bytes(content)
    return path
