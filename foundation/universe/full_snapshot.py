from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from foundation.universe.snapshot import validate_snapshot


class FullSnapshotError(ValueError):
    """Raised when exchange and broker identities cannot be reconciled safely."""


SEED_IDS = {"VOO": "SEC-US-VOO", "SCHD": "SEC-US-SCHD", "QQQM": "SEC-US-QQQM"}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_security_id(candidate: dict[str, Any]) -> str:
    symbol = str(candidate.get("symbol", "")).upper()
    return SEED_IDS.get(symbol, str(candidate.get("security_candidate_id", "")))


def reconcile_records(
    candidates: Iterable[dict[str, Any]],
    broker_records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_list = list(candidates)
    broker_list = list(broker_records)
    candidate_by_symbol: dict[str, dict[str, Any]] = {}
    broker_by_symbol: dict[str, dict[str, Any]] = {}

    for candidate in candidate_list:
        symbol = str(candidate.get("symbol", "")).upper()
        if not symbol or symbol in candidate_by_symbol:
            raise FullSnapshotError(f"duplicate or missing exchange symbol: {symbol or '<missing>'}")
        candidate_by_symbol[symbol] = candidate

    for broker in broker_list:
        symbol = str(broker.get("symbol", "")).upper()
        if not symbol or symbol in broker_by_symbol:
            raise FullSnapshotError(f"duplicate or missing broker symbol: {symbol or '<missing>'}")
        broker_by_symbol[symbol] = broker

    missing_broker = sorted(set(candidate_by_symbol) - set(broker_by_symbol))
    extra_broker = sorted(set(broker_by_symbol) - set(candidate_by_symbol))
    if missing_broker or extra_broker:
        raise FullSnapshotError(
            f"identity population mismatch; missing_broker={missing_broker[:10]} extra_broker={extra_broker[:10]}"
        )

    reconciled: list[dict[str, Any]] = []
    stable_ids: set[str] = set()
    robinhood_ids: set[str] = set()
    for symbol in sorted(candidate_by_symbol):
        candidate = candidate_by_symbol[symbol]
        broker = broker_by_symbol[symbol]
        candidate_id = str(candidate.get("security_candidate_id", ""))
        if broker.get("security_id") != candidate_id:
            raise FullSnapshotError(f"{symbol}: exchange/broker security identity mismatch")

        security_id = _stable_security_id(candidate)
        if not security_id or security_id in stable_ids:
            raise FullSnapshotError(f"{symbol}: duplicate or missing stable security id")
        stable_ids.add(security_id)

        broker_status = str(broker.get("broker_status", "UNKNOWN"))
        broker_eligible = broker_status == "ELIGIBLE" and broker.get("broker_eligible") is True
        instrument_id = broker.get("robinhood_instrument_id")
        if broker_eligible and not instrument_id:
            raise FullSnapshotError(f"{symbol}: eligible record lacks Robinhood instrument id")
        if instrument_id:
            if instrument_id in robinhood_ids:
                raise FullSnapshotError(f"{symbol}: duplicate Robinhood instrument id")
            robinhood_ids.add(instrument_id)

        final_state = "BROKER_ELIGIBLE" if broker_eligible else "BLOCKED"
        reason_codes = ["EXCHANGE_IDENTITY_RECONCILED"]
        if broker_eligible:
            reason_codes.extend(["ROBINHOOD_BUY_ELIGIBLE", "TAXONOMY_PENDING", "ANALYTICS_EVIDENCE_PENDING"])
        else:
            reason_codes.extend([f"ROBINHOOD_{broker_status}", "BROKER_ELIGIBILITY_BLOCKED"])

        reconciled.append({
            "security_id": security_id,
            "exchange_security_candidate_id": candidate_id,
            "symbol": symbol,
            "security_name": candidate.get("security_name"),
            "primary_exchange": candidate.get("primary_exchange"),
            "instrument_type": "ETF",
            "robinhood_instrument_id": instrument_id,
            "discovery_status": "DISCOVERED",
            "broker_status": broker_status,
            "taxonomy_status": "PENDING",
            "analytics_status": "BLOCKED",
            "final_state": final_state,
            "evidence_state": "CURRENT" if broker.get("collection_error") is None else "CONFLICTED",
            "reason_codes": reason_codes,
            "whole_share_supported": broker.get("whole_share_supported"),
            "fractional_share_supported": broker.get("fractional_share_supported"),
            "fractional_share_evidence_state": broker.get("fractional_share_evidence_state", "UNKNOWN"),
            "recurring_investment_supported": broker.get("recurring_investment_supported"),
            "recurring_investment_evidence_state": broker.get("recurring_investment_evidence_state", "UNKNOWN"),
            "dividend_reinvestment_supported": broker.get("dividend_reinvestment_supported"),
            "dividend_reinvestment_evidence_state": broker.get("dividend_reinvestment_evidence_state", "UNKNOWN"),
            "broker_verified_at_utc": broker.get("verified_at_utc"),
            "broker_source_id": broker.get("source_id"),
            "broker_source_record_id": broker.get("source_record_id"),
            "broker_content_sha256": broker.get("content_sha256"),
        })
    return reconciled


def build_full_snapshot(
    *,
    candidates: list[dict[str, Any]],
    broker_records: list[dict[str, Any]],
    operating_date: str,
    exchange_manifest: dict[str, Any],
    broker_manifest: dict[str, Any],
) -> dict[str, Any]:
    records = reconcile_records(candidates, broker_records)
    source_components = {
        "exchange_candidate_sha256": exchange_manifest.get("candidate_file_sha256"),
        "exchange_quarantine_sha256": exchange_manifest.get("quarantine_file_sha256"),
        "broker_availability_sha256": broker_manifest.get("availability_file_sha256"),
        "broker_failure_sha256": broker_manifest.get("failure_file_sha256"),
    }
    if any(not isinstance(value, str) or len(value) != 64 for value in source_components.values()):
        raise FullSnapshotError("source manifests do not contain complete SHA-256 lineage")
    source_bundle_sha256 = _sha256_bytes(json.dumps(source_components, sort_keys=True).encode("utf-8"))
    final_counts = Counter(record["final_state"] for record in records)
    snapshot = {
        "snapshot_id": f"robinhood-us-{operating_date}-full-broker-evidence",
        "operating_date": operating_date,
        "operating_timezone": "America/Chicago",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "broker_id": "ROBINHOOD-US",
        "snapshot_status": "COMPLETE",
        "snapshot_purpose": "OPERATING_SNAPSHOT",
        "lineage": {"source_bundle_sha256": source_bundle_sha256, **source_components},
        "counts": {
            "total_records": len(records),
            "discovered": len(records),
            "broker_eligible": final_counts["BROKER_ELIGIBLE"],
            "analytics_provisional": 0,
            "analytics_eligible": 0,
            "blocked": final_counts["BLOCKED"],
            "quarantined": 0,
            "excluded": 0,
        },
        "records": records,
        "attestation": {
            "recommendation_authority": False,
            "analytics_authority": False,
            "portfolio_authority": False,
            "execution_authority": False,
            "direct_uip_database_write_authority": False,
        },
    }
    errors = validate_snapshot(snapshot)
    if errors:
        raise FullSnapshotError("snapshot validation failed: " + "; ".join(errors))
    return snapshot


def write_full_snapshot(snapshot: dict[str, Any], output_path: Path) -> dict[str, Any]:
    payload = (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if output_path.exists():
        if output_path.read_bytes() != payload:
            raise FullSnapshotError(f"immutable snapshot collision: {output_path}")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)

    records = snapshot.get("records", [])
    result: dict[str, Any] = {
        "snapshot_path": str(output_path),
        "snapshot_sha256": _sha256_bytes(payload),
        "record_count": len(records) if isinstance(records, list) else 0,
    }
    if "counts" in snapshot:
        result["counts"] = snapshot["counts"]
    return result
