from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class ExchangeCollectorError(ValueError):
    """Raised when exchange discovery collection violates governed controls."""


@dataclass(frozen=True)
class SourcePayload:
    source_id: str
    url: str
    retrieved_at_utc: str
    content_sha256: str
    byte_count: int
    payload: bytes


_EXCLUDED_NAME_PATTERNS = (
    re.compile(r"\bETN\b", re.IGNORECASE),
    re.compile(r"EXCHANGE[ -]TRADED NOTE", re.IGNORECASE),
    re.compile(r"\bCLOSED[ -]END\b", re.IGNORECASE),
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_source(source_id: str, url: str, *, timeout_seconds: int = 30) -> SourcePayload:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "StocksETFIntelligencePlatform/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except Exception as exc:  # urllib surfaces several transport-specific exceptions
        raise ExchangeCollectorError(f"Unable to retrieve authoritative source: {source_id}") from exc
    if not payload:
        raise ExchangeCollectorError(f"Authoritative source returned no content: {source_id}")
    return SourcePayload(
        source_id=source_id,
        url=url,
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
        content_sha256=sha256_bytes(payload),
        byte_count=len(payload),
        payload=payload,
    )


def _truthy_etf_flag(value: str) -> bool:
    return value.strip().upper() == "Y"


def _false_test_flag(value: str) -> bool:
    return value.strip().upper() == "N"


def _looks_excluded_name(name: str) -> bool:
    return any(pattern.search(name) for pattern in _EXCLUDED_NAME_PATTERNS)


def _normalize_exchange(raw: str, source_id: str) -> str:
    value = raw.strip().upper()
    mapping = {
        "A": "NYSE_AMERICAN",
        "N": "NYSE",
        "P": "NYSE_ARCA",
        "Z": "CBOE_BZX",
        "V": "IEX",
    }
    if source_id == "NASDAQ-TRADER-NASDAQLISTED":
        return "NASDAQ"
    return mapping.get(value, value or "UNKNOWN")


def parse_symbol_directory(payload: SourcePayload) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = payload.payload.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    if not reader.fieldnames:
        raise ExchangeCollectorError(f"Missing header in source: {payload.source_id}")

    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for row_number, row in enumerate(reader, start=2):
        normalized = {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
        if any(value.startswith("File Creation Time") for value in normalized.values()):
            continue

        symbol = normalized.get("Symbol") or normalized.get("ACT Symbol") or normalized.get("NASDAQ Symbol") or ""
        name = normalized.get("Security Name") or ""
        etf_flag = normalized.get("ETF") or ""
        test_flag = normalized.get("Test Issue") or ""
        exchange_code = normalized.get("Exchange") or ""

        source_record = {
            "source_id": payload.source_id,
            "source_url": payload.url,
            "source_row_number": row_number,
            "source_record": normalized,
            "source_content_sha256": payload.content_sha256,
            "retrieved_at_utc": payload.retrieved_at_utc,
        }

        if not symbol:
            quarantined.append({**source_record, "quarantine_reason": "MISSING_SYMBOL"})
            continue
        if not _truthy_etf_flag(etf_flag):
            continue
        if not _false_test_flag(test_flag):
            quarantined.append({**source_record, "symbol": symbol, "quarantine_reason": "TEST_OR_UNKNOWN_TEST_FLAG"})
            continue
        if not name:
            quarantined.append({**source_record, "symbol": symbol, "quarantine_reason": "MISSING_SECURITY_NAME"})
            continue
        if _looks_excluded_name(name):
            quarantined.append({**source_record, "symbol": symbol, "security_name": name, "quarantine_reason": "EXCLUDED_NOTE_OR_CLOSED_END_PATTERN"})
            continue

        candidates.append(
            {
                "security_candidate_id": f"US-ETF-{symbol.upper()}",
                "symbol": symbol.upper(),
                "security_name": name,
                "primary_exchange": _normalize_exchange(exchange_code, payload.source_id),
                "instrument_type": "ETF_CANDIDATE",
                "candidate_state": "DISCOVERY_CANDIDATE",
                "certified_discovery": False,
                "robinhood_eligible": False,
                "analytics_eligible": False,
                **source_record,
            }
        )
    return candidates, quarantined


def reconcile_candidates(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_symbol.setdefault(record["symbol"], []).append(record)

    accepted: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for symbol, group in sorted(by_symbol.items()):
        identities = {(r["security_name"], r["primary_exchange"]) for r in group}
        if len(identities) > 1:
            quarantined.append(
                {
                    "symbol": symbol,
                    "quarantine_reason": "CONFLICTING_EXCHANGE_IDENTITY",
                    "candidate_records": group,
                }
            )
            continue
        chosen = sorted(group, key=lambda r: (r["source_id"], r["source_row_number"]))[0]
        chosen = dict(chosen)
        chosen["corroborating_source_ids"] = sorted({r["source_id"] for r in group})
        chosen["source_record_count"] = len(group)
        accepted.append(chosen)
    return accepted, quarantined


def write_collection(
    *,
    source_payloads: Iterable[SourcePayload],
    candidates: Iterable[dict[str, Any]],
    quarantined: Iterable[dict[str, Any]],
    output_root: Path,
    operating_date: str,
) -> dict[str, Any]:
    payloads = list(source_payloads)
    accepted = list(candidates)
    quarantine = list(quarantined)
    raw_root = output_root / "raw" / operating_date
    staged_root = output_root / "staged" / operating_date
    quarantine_root = output_root / "quarantine" / operating_date
    raw_root.mkdir(parents=True, exist_ok=True)
    staged_root.mkdir(parents=True, exist_ok=True)
    quarantine_root.mkdir(parents=True, exist_ok=True)

    for payload in payloads:
        safe_name = payload.source_id.lower().replace("-", "_") + ".txt"
        raw_path = raw_root / safe_name
        if raw_path.exists() and raw_path.read_bytes() != payload.payload:
            raise ExchangeCollectorError(f"Immutable raw payload collision: {raw_path}")
        raw_path.write_bytes(payload.payload)

    accepted_path = staged_root / "us_etf_discovery_candidates.json"
    quarantine_path = quarantine_root / "us_etf_discovery_quarantine.json"
    manifest_path = staged_root / "collection_manifest.json"
    accepted_path.write_text(json.dumps(accepted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    quarantine_path.write_text(json.dumps(quarantine, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "collector_id": "US-ETF-EXCHANGE-DISCOVERY",
        "operating_date": operating_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_count": len(payloads),
        "candidate_count": len(accepted),
        "quarantine_count": len(quarantine),
        "candidate_is_certified_discovery": False,
        "candidate_implies_robinhood_eligibility": False,
        "sources": [
            {
                "source_id": p.source_id,
                "url": p.url,
                "retrieved_at_utc": p.retrieved_at_utc,
                "content_sha256": p.content_sha256,
                "byte_count": p.byte_count,
            }
            for p in payloads
        ],
        "candidate_file": str(accepted_path),
        "candidate_file_sha256": sha256_bytes(accepted_path.read_bytes()),
        "quarantine_file": str(quarantine_path),
        "quarantine_file_sha256": sha256_bytes(quarantine_path.read_bytes()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
