from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_adjusted_series(raw_path: Path) -> tuple[str, list[tuple[str, float]]]:
    payload = raw_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    document = json.loads(payload.decode("utf-8"))
    results = ((document.get("chart") or {}).get("result") or [])
    if not results:
        raise ValueError("RAW_PAYLOAD_HAS_NO_RESULT")
    result = results[0]
    timestamps = list(result.get("timestamp") or [])
    adjusted_rows = ((result.get("indicators") or {}).get("adjclose") or [])
    adjusted = list((adjusted_rows[0] if adjusted_rows else {}).get("adjclose") or [])
    series: list[tuple[str, float]] = []
    for index, timestamp in enumerate(timestamps):
        if timestamp is None or index >= len(adjusted) or adjusted[index] is None:
            continue
        price = float(adjusted[index])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("NONPOSITIVE_OR_NONFINITE_ADJUSTED_PRICE")
        observation_date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
        series.append((observation_date, price))
    if not series:
        raise ValueError("NO_VALID_ADJUSTED_PRICE_OBSERVATIONS")
    dates = [item[0] for item in series]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("ADJUSTED_SERIES_NOT_STRICTLY_CHRONOLOGICAL")
    return digest, series


def calculate_horizon(
    *,
    series: list[tuple[str, float]],
    horizon: str,
    minimum_observations: int,
    annualized: bool,
    day_basis: float,
) -> dict[str, Any]:
    if len(series) < minimum_observations:
        raise ValueError("INSUFFICIENT_OBSERVATIONS_FOR_AUTHORIZED_HORIZON")
    window = series[-minimum_observations:]
    start_date, start_price = window[0]
    end_date, end_price = window[-1]
    cumulative_return = (end_price / start_price) - 1.0
    elapsed_days = (
        datetime.fromisoformat(end_date).date() - datetime.fromisoformat(start_date).date()
    ).days
    if elapsed_days <= 0:
        raise ValueError("NONPOSITIVE_RETURN_WINDOW_DAYS")
    annualized_return = None
    if annualized:
        annualized_return = (1.0 + cumulative_return) ** (float(day_basis) / elapsed_days) - 1.0
    return {
        "horizon": horizon,
        "calculation_state": "CALCULATED",
        "return_basis": "ADJUSTED_CLOSE_TOTAL_RETURN",
        "observation_count": len(window),
        "start_date": start_date,
        "end_date": end_date,
        "start_adjusted_price": start_price,
        "end_adjusted_price": end_price,
        "elapsed_days": elapsed_days,
        "cumulative_total_return": cumulative_return,
        "annualized_total_return": annualized_return,
        "interpolation_used": False,
        "imputation_used": False,
    }


def _blocked_record(
    certification_record: dict[str, Any],
    *,
    digest: str | None,
    policy: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    horizons = {
        horizon: {
            "horizon": horizon,
            "calculation_state": "CALCULATION_BLOCKED",
            "reason": reason,
        }
        for horizon in policy["horizon_minimum_observations"]
    }
    return {
        "security_id": str(certification_record.get("security_id") or ""),
        "symbol": str(certification_record.get("symbol") or "").upper(),
        "evidence_state": certification_record.get("evidence_state"),
        "calculation_state": "CALCULATION_BLOCKED",
        "calculation_reasons": [reason],
        "source_payload_sha256": digest or certification_record.get("source_payload_sha256"),
        "latest_adjusted_price_date": None,
        "available_adjusted_observations": 0,
        "horizons": horizons,
        "authority": {
            "return_calculation": False,
            "risk_analytics": False,
            "benchmark_comparison": False,
            "forecasting": False,
            "ranking": False,
            "recommendations": False,
        },
    }


def calculate_record(
    certification_record: dict[str, Any],
    *,
    raw_root: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    security_id = str(certification_record.get("security_id") or "")
    symbol = str(certification_record.get("symbol") or "").upper()
    evidence_state = certification_record.get("evidence_state")
    if evidence_state not in policy["required_evidence_states"]:
        raise ValueError(f"EVIDENCE_STATE_NOT_AUTHORIZED:{evidence_state}")
    raw_path = raw_root / f"{security_id}.json"
    if not raw_path.exists():
        raise ValueError("RAW_PAYLOAD_MISSING")

    raw_digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if raw_digest != certification_record.get("source_payload_sha256"):
        raise ValueError("CERTIFICATION_SOURCE_HASH_MISMATCH")

    try:
        digest, series = _load_adjusted_series(raw_path)
    except ValueError as exc:
        reason = str(exc)
        if reason in {
            "NONPOSITIVE_OR_NONFINITE_ADJUSTED_PRICE",
            "NO_VALID_ADJUSTED_PRICE_OBSERVATIONS",
            "ADJUSTED_SERIES_NOT_STRICTLY_CHRONOLOGICAL",
        }:
            return _blocked_record(
                certification_record,
                digest=raw_digest,
                policy=policy,
                reason=reason,
            )
        raise

    eligible = certification_record.get("eligible_horizons") or {}
    horizons: dict[str, Any] = {}
    for horizon, minimum in policy["horizon_minimum_observations"].items():
        if eligible.get(horizon) is not True:
            horizons[horizon] = {
                "horizon": horizon,
                "calculation_state": "NOT_AUTHORIZED",
                "reason": "PHASE_3_4_HORIZON_NOT_ELIGIBLE",
            }
            continue
        horizons[horizon] = calculate_horizon(
            series=series,
            horizon=horizon,
            minimum_observations=int(minimum),
            annualized=horizon in set(policy["annualized_horizons"]),
            day_basis=float(policy["annualization_day_basis"]),
        )

    return {
        "security_id": security_id,
        "symbol": symbol,
        "evidence_state": evidence_state,
        "calculation_state": "CALCULATED",
        "calculation_reasons": [],
        "source_payload_sha256": digest,
        "latest_adjusted_price_date": series[-1][0],
        "available_adjusted_observations": len(series),
        "horizons": horizons,
        "authority": {
            "return_calculation": True,
            "risk_analytics": False,
            "benchmark_comparison": False,
            "forecasting": False,
            "ranking": False,
            "recommendations": False,
        },
    }


def calculate_universe(
    certification_document: dict[str, Any],
    *,
    raw_root: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    records = list(certification_document.get("records") or [])
    expected = int(policy["required_record_count"])
    if len(records) != expected:
        raise ValueError(f"EXPECTED_{expected}_RECORDS_FOUND_{len(records)}")
    ids = [str(record.get("security_id") or "") for record in records]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_OR_MISSING_SECURITY_ID")
    outputs = [calculate_record(record, raw_root=raw_root, policy=policy) for record in records]
    horizon_counts = {name: 0 for name in policy["horizon_minimum_observations"]}
    state_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for record in outputs:
        state = record["calculation_state"]
        state_counts[state] = state_counts.get(state, 0) + 1
        for reason in record.get("calculation_reasons") or []:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for horizon, result in record["horizons"].items():
            if result["calculation_state"] == "CALCULATED":
                horizon_counts[horizon] += 1
    return {
        "phase": "3.5",
        "record_count": len(outputs),
        "records": outputs,
        "horizon_calculated_counts": horizon_counts,
        "calculation_state_counts": dict(sorted(state_counts.items())),
        "calculation_reason_counts": dict(sorted(reason_counts.items())),
        "return_basis": policy["return_basis"],
        "authority": policy["authority"],
    }
