from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _parse_payload(path: Path) -> tuple[bytes, dict[str, Any]]:
    payload = path.read_bytes()
    return payload, json.loads(payload.decode("utf-8"))


def _extract_series(document: dict[str, Any]) -> tuple[list[int], list[Any], list[Any], dict[str, Any]]:
    chart = document.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        raise ValueError("RAW_PAYLOAD_HAS_NO_RESULT")
    result = results[0]
    timestamps = list(result.get("timestamp") or [])
    indicators = result.get("indicators") or {}
    quote_rows = indicators.get("quote") or []
    adjusted_rows = indicators.get("adjclose") or []
    closes = list((quote_rows[0] if quote_rows else {}).get("close") or [])
    adjusted = list((adjusted_rows[0] if adjusted_rows else {}).get("adjclose") or [])
    return timestamps, closes, adjusted, result


def certify_record(
    record: dict[str, Any],
    *,
    raw_root: Path,
    operating_date: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    security_id = str(record.get("security_id") or "")
    symbol = str(record.get("symbol") or "").upper()
    raw_path_value = ((record.get("source_lineage") or {}).get("raw_path") or "")
    raw_path = raw_root / Path(raw_path_value).name

    if record.get("collection_status") != policy["required_collection_status"]:
        reasons.append("COLLECTION_STATUS_NOT_CERTIFIABLE")
    if record.get("provider_id") != policy["required_provider_id"]:
        reasons.append("PROVIDER_ID_MISMATCH")
    if str(record.get("provider_symbol") or "").upper() != symbol:
        reasons.append("PROVIDER_SYMBOL_MISMATCH")
    if record.get("provider_data_granularity") != policy["required_provider_data_granularity"]:
        reasons.append("GRANULARITY_MISMATCH")
    if not raw_path.exists():
        reasons.append("RAW_PAYLOAD_MISSING")
        return _result(record, reasons, policy)

    try:
        payload, document = _parse_payload(raw_path)
    except Exception:
        reasons.append("RAW_PAYLOAD_UNREADABLE")
        return _result(record, reasons, policy)

    digest = hashlib.sha256(payload).hexdigest()
    if digest != record.get("payload_sha256"):
        reasons.append("PAYLOAD_HASH_MISMATCH")
    if digest != ((record.get("source_lineage") or {}).get("payload_sha256")):
        reasons.append("LINEAGE_HASH_MISMATCH")

    try:
        timestamps, closes, adjusted, result = _extract_series(document)
    except ValueError as exc:
        reasons.append(str(exc))
        return _result(record, reasons, policy)

    meta = result.get("meta") or {}
    if str(meta.get("symbol") or "").upper() != symbol:
        reasons.append("RAW_PROVIDER_SYMBOL_MISMATCH")
    if meta.get("dataGranularity") != policy["required_provider_data_granularity"]:
        reasons.append("RAW_GRANULARITY_MISMATCH")

    valid_indices = [i for i, ts in enumerate(timestamps) if ts is not None and i < len(closes) and closes[i] is not None]
    valid_timestamps = [int(timestamps[i]) for i in valid_indices]
    observation_dates = [datetime.utcfromtimestamp(ts).date().isoformat() for ts in valid_timestamps]

    if valid_timestamps != sorted(valid_timestamps):
        reasons.append("OBSERVATIONS_NOT_CHRONOLOGICAL")
    if len(observation_dates) != len(set(observation_dates)):
        reasons.append("DUPLICATE_OBSERVATION_DATES")

    operating = date.fromisoformat(operating_date)
    if any(date.fromisoformat(value) > operating for value in observation_dates):
        reasons.append("FUTURE_OBSERVATION_DATE")

    adjusted_count = sum(1 for i in valid_indices if i < len(adjusted) and adjusted[i] is not None)
    if adjusted_count != len(valid_indices):
        reasons.append("INCOMPLETE_ADJUSTED_PRICE_COVERAGE")
    if int(record.get("observation_count") or 0) != len(valid_indices):
        reasons.append("OBSERVATION_COUNT_MISMATCH")
    if int(record.get("adjusted_price_observation_count") or 0) != adjusted_count:
        reasons.append("ADJUSTED_COUNT_MISMATCH")

    expected_first = observation_dates[0] if observation_dates else None
    expected_latest = observation_dates[-1] if observation_dates else None
    if record.get("first_observation_date") != expected_first:
        reasons.append("FIRST_OBSERVATION_DATE_MISMATCH")
    if record.get("latest_observation_date") != expected_latest:
        reasons.append("LATEST_OBSERVATION_DATE_MISMATCH")
    if expected_latest is None:
        reasons.append("NO_VALID_OBSERVATIONS")
    elif (operating - date.fromisoformat(expected_latest)).days > int(policy["evidence_controls"]["latest_observation_max_age_days"]):
        reasons.append("STALE_LATEST_OBSERVATION")

    events = result.get("events") or {}
    for key in ("dividends", "splits"):
        value = events.get(key) or {}
        if not isinstance(value, dict):
            reasons.append(f"INVALID_{key.upper()}_EVENT_SHAPE")

    return _result(record, reasons, policy)


def _result(record: dict[str, Any], reasons: list[str], policy: dict[str, Any]) -> dict[str, Any]:
    observation_count = int(record.get("observation_count") or 0)
    horizons = {
        name: observation_count >= int(minimum)
        for name, minimum in policy["horizon_minimum_observations"].items()
    }
    critical = bool(reasons)
    if critical:
        state = "QUARANTINED"
        horizons = {name: False for name in horizons}
    elif all(horizons.values()):
        state = "EVIDENCE_CERTIFIED"
    else:
        state = "HORIZON_LIMITED"
    return {
        "security_id": record.get("security_id"),
        "symbol": record.get("symbol"),
        "evidence_state": state,
        "observation_count": observation_count,
        "eligible_horizons": horizons,
        "certification_reasons": sorted(set(reasons)),
        "source_payload_sha256": record.get("payload_sha256"),
        "authority": {
            "return_calculation": False,
            "risk_analytics": False,
            "forecasting": False,
            "ranking": False,
            "recommendations": False,
        },
    }


def certify_universe(
    records: list[dict[str, Any]],
    *,
    raw_root: Path,
    operating_date: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    expected = int(policy["required_record_count"])
    if len(records) != expected:
        raise ValueError(f"EXPECTED_{expected}_RECORDS_FOUND_{len(records)}")
    ids = [str(record.get("security_id") or "") for record in records]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("DUPLICATE_OR_MISSING_SECURITY_ID")

    results = [
        certify_record(record, raw_root=raw_root, operating_date=operating_date, policy=policy)
        for record in records
    ]
    symbols = {str(item.get("symbol") or "").upper() for item in results}
    missing_seeds = sorted(set(policy["required_seed_symbols"]) - symbols)
    if missing_seeds:
        raise ValueError(f"MISSING_REQUIRED_SEEDS:{','.join(missing_seeds)}")

    state_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    horizon_counts = {name: 0 for name in policy["horizon_minimum_observations"]}
    for item in results:
        state_counts[item["evidence_state"]] = state_counts.get(item["evidence_state"], 0) + 1
        for reason in item["certification_reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for horizon, eligible in item["eligible_horizons"].items():
            if eligible:
                horizon_counts[horizon] += 1

    return {
        "phase": "3.4",
        "operating_date": operating_date,
        "record_count": len(results),
        "records": results,
        "state_counts": dict(sorted(state_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "horizon_eligible_counts": horizon_counts,
        "all_input_records_preserved": len(results) == len(records),
        "authority": policy["authority"],
    }
