from __future__ import annotations

import hashlib
import json
import statistics
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
class CollectionResult:
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
    query = urllib.parse.urlencode(
        {
            "interval": policy["interval"],
            "range": policy["range"],
            "events": ",".join(policy["events"]),
            "includeAdjustedClose": "true",
        }
    )
    return f"{base}?{query}"


def parse_chart_payload(
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
        return _base_record(security_id, requested_symbol, requested_symbol, "ERROR", retrieved_at_utc, digest, source_url, raw_path)

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
    adjusted = adj_rows[0].get("adjclose", []) if adj_rows else []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    valid_indices = [i for i, ts in enumerate(timestamps) if ts is not None and i < len(closes) and closes[i] is not None]
    latest_date = None
    if valid_indices:
        latest_ts = timestamps[valid_indices[-1]]
        latest_date = datetime.fromtimestamp(latest_ts, tz=timezone.utc).date().isoformat()

    dollar_volumes: list[float] = []
    observed_volumes: list[float] = []
    for i in valid_indices:
        if i < len(volumes) and volumes[i] is not None:
            volume = float(volumes[i])
            close = float(closes[i])
            observed_volumes.append(volume)
            dollar_volumes.append(max(0.0, volume * close))

    zero_ratio = None
    if observed_volumes:
        zero_ratio = sum(1 for value in observed_volumes if value == 0) / len(observed_volumes)

    adjusted_available = any(value is not None for value in adjusted)
    median_dollar_volume = statistics.median(dollar_volumes) if dollar_volumes else None

    return {
        **_base_record(security_id, requested_symbol, provider_symbol, status, retrieved_at_utc, digest, source_url, raw_path),
        "observation_count": len(valid_indices),
        "latest_observation_date": latest_date,
        "adjusted_price_available": adjusted_available,
        "volume_observation_count": len(observed_volumes),
        "median_daily_dollar_volume": median_dollar_volume,
        "zero_volume_ratio": zero_ratio,
    }


def _base_record(
    security_id: str,
    symbol: str,
    provider_symbol: str,
    status: str,
    retrieved_at_utc: str,
    digest: str,
    source_url: str,
    raw_path: str,
) -> dict[str, Any]:
    return {
        "security_id": security_id,
        "symbol": symbol.upper(),
        "provider_id": PROVIDER_ID,
        "provider_symbol": provider_symbol.upper(),
        "collection_status": status,
        "retrieved_at_utc": retrieved_at_utc,
        "payload_sha256": digest,
        "observation_count": 0,
        "latest_observation_date": None,
        "adjusted_price_available": False,
        "volume_observation_count": 0,
        "median_daily_dollar_volume": None,
        "zero_volume_ratio": None,
        "source_lineage": {
            "source_url": source_url,
            "raw_path": raw_path,
            "payload_sha256": digest,
        },
        "authority": {
            "market_screen": True,
            "analytics": False,
            "forecasting": False,
            "recommendations": False,
            "automatic_execution": False,
        },
    }


def collect_symbol(
    *,
    security_id: str,
    symbol: str,
    policy: dict[str, Any],
    user_agent: str,
    raw_path: Path,
) -> CollectionResult:
    url = build_url(symbol, policy)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    last_error: Exception | None = None
    payload = b""

    for attempt in range(policy["retry_attempts"]):
        try:
            with urllib.request.urlopen(request, timeout=policy["timeout_seconds"]) as response:
                payload = response.read()
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 >= policy["retry_attempts"]:
                raise RuntimeError(f"Collection failed for {symbol}: {exc}") from exc
            time.sleep(policy["retry_backoff_seconds"][attempt])

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and raw_path.read_bytes() != payload:
        raise RuntimeError(f"Immutable raw payload collision: {raw_path}")
    raw_path.write_bytes(payload)
    retrieved = _utc_now()
    record = parse_chart_payload(
        payload,
        security_id=security_id,
        requested_symbol=symbol.upper(),
        source_url=url,
        raw_path=str(raw_path),
        retrieved_at_utc=retrieved,
    )
    return CollectionResult(record=record, raw_payload=payload)
