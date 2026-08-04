from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVIDER_ID = "YAHOO_FINANCE_CHART"


@dataclass(frozen=True)
class HistoricalCollectionResult:
    record: dict[str, Any]
    raw_payload: bytes


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if not value or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in value):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return value


def build_url(symbol: str, policy: dict[str, Any]) -> str:
    safe = _safe_symbol(symbol)
    base = policy["endpoint_template"].format(symbol=urllib.parse.quote(safe))
    query = urllib.parse.urlencode({
        "interval": policy["interval"],
        "range": policy["range"],
        "events": ",".join(policy["events"]),
        "includeAdjustedClose": "true",
    })
    return f"{base}?{query}"


def _base_record(
    security_id: str,
    symbol: str,
    provider_symbol: str,
    status: str,
    retrieved_at_utc: str,
    digest: str,
    source_url: str,
    raw_path: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "security_id": security_id,
        "symbol": symbol.upper(),
        "provider_id": PROVIDER_ID,
        "provider_symbol": provider_symbol.upper(),
        "collection_status": status,
        "collection_error": error,
        "retrieved_at_utc": retrieved_at_utc,
        "payload_sha256": digest,
        "observation_count": 0,
        "first_observation_date": None,
        "latest_observation_date": None,
        "adjusted_price_observation_count": 0,
        "dividend_event_count": 0,
        "split_event_count": 0,
        "source_lineage": {
            "source_url": source_url,
            "raw_path": raw_path,
            "payload_sha256": digest,
        },
        "authority": {
            "historical_data_collection": True,
            "historical_data_normalization": True,
            "return_calculation": False,
            "risk_analytics": False,
            "forecasting": False,
            "ranking": False,
            "recommendations": False,
            "automatic_execution": False,
        },
    }


def parse_historical_payload(
    payload: bytes,
    *,
    security_id: str,
    requested_symbol: str,
    source_url: str,
    raw_path: str,
    retrieved_at_utc: str,
) -> dict[str, Any]:
    digest = hashlib.sha256(payload).hexdigest()
    document = json.loads(payload.decode("utf-8"))
    chart = document.get("chart") or {}
    if chart.get("error"):
        error = json.dumps(chart["error"], sort_keys=True)
        return _base_record(security_id, requested_symbol, requested_symbol, "PROVIDER_ERROR", retrieved_at_utc, digest, source_url, raw_path, error)
    results = chart.get("result") or []
    if not results:
        return _base_record(security_id, requested_symbol, requested_symbol, "NOT_FOUND", retrieved_at_utc, digest, source_url, raw_path)

    result = results[0]
    meta = result.get("meta") or {}
    provider_symbol = str(meta.get("symbol") or requested_symbol).upper()
    status = "COLLECTED" if provider_symbol == requested_symbol.upper() else "SYMBOL_MISMATCH"
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_rows = indicators.get("quote") or []
    adj_rows = indicators.get("adjclose") or []
    quote = quote_rows[0] if quote_rows else {}
    closes = quote.get("close") or []
    adjusted = adj_rows[0].get("adjclose", []) if adj_rows else []
    valid_indices = [i for i, ts in enumerate(timestamps) if ts is not None and i < len(closes) and closes[i] is not None]
    dates = [datetime.fromtimestamp(timestamps[i], tz=timezone.utc).date().isoformat() for i in valid_indices]
    adjusted_count = sum(1 for i in valid_indices if i < len(adjusted) and adjusted[i] is not None)
    events = result.get("events") or {}
    dividends = events.get("dividends") or {}
    splits = events.get("splits") or {}

    record = _base_record(security_id, requested_symbol, provider_symbol, status, retrieved_at_utc, digest, source_url, raw_path)
    record.update({
        "observation_count": len(valid_indices),
        "first_observation_date": dates[0] if dates else None,
        "latest_observation_date": dates[-1] if dates else None,
        "adjusted_price_observation_count": adjusted_count,
        "dividend_event_count": len(dividends),
        "split_event_count": len(splits),
    })
    return record


def collect_symbol(
    *,
    security_id: str,
    symbol: str,
    policy: dict[str, Any],
    user_agent: str,
    raw_path: Path,
) -> HistoricalCollectionResult:
    url = build_url(symbol, policy)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    payload = b""
    last_error: Exception | None = None
    for attempt in range(int(policy["retry_attempts"])):
        try:
            with urllib.request.urlopen(request, timeout=int(policy["timeout_seconds"])) as response:
                payload = response.read()
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 >= int(policy["retry_attempts"]):
                retrieved = _utc_now()
                error_payload = json.dumps({"provider_error": str(exc)}).encode("utf-8")
                digest = hashlib.sha256(error_payload).hexdigest()
                record = _base_record(security_id, symbol, symbol, "PROVIDER_ERROR", retrieved, digest, url, str(raw_path), str(exc))
                return HistoricalCollectionResult(record=record, raw_payload=error_payload)
            time.sleep(float(policy["retry_backoff_seconds"][attempt]))
    if not payload and last_error is not None:
        raise RuntimeError(f"Historical collection failed for {symbol}: {last_error}")

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and raw_path.read_bytes() != payload:
        raise RuntimeError(f"Immutable raw payload collision: {raw_path}")
    raw_path.write_bytes(payload)
    retrieved = _utc_now()
    record = parse_historical_payload(
        payload,
        security_id=security_id,
        requested_symbol=symbol,
        source_url=url,
        raw_path=str(raw_path),
        retrieved_at_utc=retrieved,
    )
    return HistoricalCollectionResult(record=record, raw_payload=payload)
