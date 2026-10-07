from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from foundation.market.market_data_screen import MarketDataScreenError, screen_record

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "market" / "market_data_eligibility_classification_policy.json"


class MarketDataEligibilityError(ValueError):
    """Raised when Phase 2B.4 classification violates governed requirements."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("phase") != "2" or policy.get("subphase") != "2B.4":
        raise MarketDataEligibilityError("Unexpected eligibility classification phase")
    if policy.get("required_input_record_count") != 4419:
        raise MarketDataEligibilityError("Certified active-universe count drifted")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise MarketDataEligibilityError("Evidence-determined sizing is required")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise MarketDataEligibilityError("Arbitrary universe targets are prohibited")
    if policy.get("preserve_all_input_records") is not True:
        raise MarketDataEligibilityError("All input records must be preserved")
    if policy.get("destructive_deletion_allowed") is not False:
        raise MarketDataEligibilityError("Destructive deletion is prohibited")
    if policy.get("fail_closed") is not True:
        raise MarketDataEligibilityError("Classification must fail closed")
    authority = policy.get("authority", {})
    forbidden = (
        "full_history_collection",
        "analytics",
        "forecasting",
        "ranking",
        "recommendations",
        "portfolio_allocation",
        "uip_export",
        "automatic_execution",
        "direct_uip_database_writes",
    )
    if any(authority.get(key) is not False for key in forbidden):
        raise MarketDataEligibilityError("Classification improperly expands authority")
    return policy


def _payload_chart_result(payload: bytes) -> dict[str, Any]:
    document = json.loads(payload.decode("utf-8"))
    chart = document.get("chart") or {}
    if chart.get("error"):
        raise MarketDataEligibilityError("Collected payload contains a provider error")
    results = chart.get("result") or []
    if len(results) != 1:
        raise MarketDataEligibilityError("Collected payload must contain one chart result")
    return results[0]


def _corporate_action_state(result: dict[str, Any]) -> str:
    events = result.get("events") or {}
    for event_type in ("dividends", "splits"):
        values = events.get(event_type) or {}
        if not isinstance(values, dict):
            return "CONFLICTED"
        seen: set[str] = set()
        for key, event in values.items():
            if not isinstance(event, dict):
                return "CONFLICTED"
            event_date = str(event.get("date") or key)
            if event_date in seen:
                return "CONFLICTED"
            seen.add(event_date)
    return "CLEAR"


def build_screen_input(
    record: dict[str, Any],
    *,
    raw_payload: bytes,
    operating_date: date,
) -> dict[str, Any]:
    if record.get("collection_status") != "COLLECTED":
        raise MarketDataEligibilityError("Only COLLECTED records can build screen evidence")
    expected_hash = str(record.get("payload_sha256") or "")
    actual_hash = hashlib.sha256(raw_payload).hexdigest()
    if expected_hash != actual_hash:
        raise MarketDataEligibilityError("Raw payload hash does not match checkpoint lineage")

    result = _payload_chart_result(raw_payload)
    meta = result.get("meta") or {}
    provider_symbol = str(meta.get("symbol") or "").upper()
    requested_symbol = str(record.get("symbol") or "").upper()
    if provider_symbol != requested_symbol:
        raise MarketDataEligibilityError("Provider symbol does not match requested symbol")

    timestamps = list(result.get("timestamp") or [])
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    quote = quotes[0] if quotes else {}
    closes = list(quote.get("close") or [])
    valid_rows = [
        index
        for index, timestamp in enumerate(timestamps)
        if timestamp is not None and index < len(closes) and closes[index] is not None
    ]
    if not timestamps or not valid_rows:
        raise MarketDataEligibilityError("Collected payload lacks usable price observations")

    start = datetime.fromtimestamp(timestamps[valid_rows[0]], tz=timezone.utc).date()
    end = datetime.fromtimestamp(timestamps[valid_rows[-1]], tz=timezone.utc).date()
    expected_sessions = sum(1 for timestamp in timestamps if timestamp is not None)
    observed_sessions = len(valid_rows)
    coverage = observed_sessions / expected_sessions

    latest_record_date = date.fromisoformat(str(record.get("latest_observation_date")))
    if latest_record_date != end:
        raise MarketDataEligibilityError("Latest observation date does not reconcile")
    if int(record.get("observation_count", -1)) != observed_sessions:
        raise MarketDataEligibilityError("Observation count does not reconcile")

    lineage = record.get("source_lineage") or {}
    retrieved_at = str(record.get("retrieved_at_utc") or "")
    if not retrieved_at:
        raise MarketDataEligibilityError("Retrieval timestamp is required")

    median_volume = record.get("median_daily_dollar_volume")
    zero_ratio = record.get("zero_volume_ratio")
    if median_volume is None or zero_ratio is None:
        raise MarketDataEligibilityError("Liquidity evidence is required")

    return {
        "security_id": record["security_id"],
        "symbol": requested_symbol,
        "processing_state": "ACTIVE_STRUCTURAL_UNIVERSE",
        "observation_start_date": start.isoformat(),
        "observation_end_date": end.isoformat(),
        "price_observation_count": observed_sessions,
        "expected_trading_session_count": expected_sessions,
        "expected_session_coverage_ratio": coverage,
        "latest_observation_age_calendar_days": (operating_date - end).days,
        "adjusted_price_available": bool(record.get("adjusted_price_available")),
        "median_daily_dollar_volume_usd": float(median_volume),
        "zero_volume_session_ratio": float(zero_ratio),
        "corporate_action_conflict_state": _corporate_action_state(result),
        "source_lineage": {
            "source_id": str(record.get("provider_id") or "YAHOO_FINANCE_CHART"),
            "retrieved_at_utc": retrieved_at,
            "content_sha256": actual_hash,
            "source_url": lineage.get("source_url"),
            "raw_path": lineage.get("raw_path"),
        },
    }


def classify_record(
    record: dict[str, Any],
    *,
    operating_date: date,
    raw_payload: bytes | None = None,
) -> dict[str, Any]:
    policy = load_policy()
    status = str(record.get("collection_status") or "")
    if status != policy["required_collection_status"]:
        mapped = policy["collection_status_mapping"].get(status)
        if mapped is None:
            raise MarketDataEligibilityError(f"Unknown collection status: {status}")
        return {
            **record,
            "screen_state": mapped,
            "screen_reasons": [f"COLLECTION_STATUS_{status}"],
            "analytics_authorized": False,
            "forecasting_authorized": False,
            "recommendations_authorized": False,
            "automatic_execution_authorized": False,
        }
    if raw_payload is None:
        raise MarketDataEligibilityError("Raw payload is required for a collected record")
    evidence = build_screen_input(record, raw_payload=raw_payload, operating_date=operating_date)
    try:
        return screen_record(evidence, operating_date)
    except MarketDataScreenError as exc:
        raise MarketDataEligibilityError(str(exc)) from exc


def classify_universe(
    records: list[dict[str, Any]],
    *,
    operating_date: date,
    raw_root: Path,
) -> dict[str, Any]:
    policy = load_policy()
    if len(records) != int(policy["required_input_record_count"]):
        raise MarketDataEligibilityError("Input record count does not match the certified universe")

    seen_ids: set[str] = set()
    classified: list[dict[str, Any]] = []
    for record in records:
        security_id = str(record.get("security_id") or "")
        if not security_id or security_id in seen_ids:
            raise MarketDataEligibilityError("Stable security IDs must be unique")
        seen_ids.add(security_id)
        raw_payload = None
        if record.get("collection_status") == "COLLECTED":
            raw_path = Path(str((record.get("source_lineage") or {}).get("raw_path") or ""))
            if not raw_path.is_absolute():
                raw_path = raw_root / raw_path.name
            if not raw_path.exists():
                raise MarketDataEligibilityError(f"Raw payload is missing for {security_id}")
            raw_payload = raw_path.read_bytes()
        classified.append(classify_record(record, operating_date=operating_date, raw_payload=raw_payload))

    symbols = {str(record.get("symbol") or "").upper() for record in classified}
    missing_seeds = [symbol for symbol in policy["required_seed_symbols"] if symbol not in symbols]
    if missing_seeds:
        raise MarketDataEligibilityError(f"Required seed ETFs are missing: {', '.join(missing_seeds)}")

    counts = Counter(record["screen_state"] for record in classified)
    reason_counts = Counter(reason for record in classified for reason in record.get("screen_reasons", []))
    return {
        "phase": "2B.4",
        "operating_date": operating_date.isoformat(),
        "total_input_records": len(records),
        "total_classified_records": len(classified),
        "screen_state_counts": dict(sorted(counts.items())),
        "screen_reason_counts": dict(sorted(reason_counts.items())),
        "required_seed_symbols": list(policy["required_seed_symbols"]),
        "selection_principle": policy["selection_principle"],
        "target_universe_size": None,
        "input_universe_preserved": True,
        "destructive_deletion_allowed": False,
        "full_history_collection_authorized": False,
        "analytics_authorized": False,
        "forecasting_authorized": False,
        "records": classified,
    }
