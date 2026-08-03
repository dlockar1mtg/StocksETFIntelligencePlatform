from __future__ import annotations

import json
from pathlib import Path


class SecurityMasterValidationError(ValueError):
    pass


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityMasterValidationError(f"Unable to load valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SecurityMasterValidationError("Expected a JSON object")
    return data


def validate_security_master(master: dict) -> None:
    if master.get("unknown_security_blocked") is not True:
        raise SecurityMasterValidationError("Unknown securities must be blocked")
    if master.get("ticker_only_identity_blocked") is not True:
        raise SecurityMasterValidationError("Ticker-only identity must be blocked")
    records = master.get("securities")
    if not isinstance(records, list) or not records:
        raise SecurityMasterValidationError("Security records are required")
    required = {"security_id", "ticker", "asset_type", "issuer_id", "fund_id", "exchange", "currency", "benchmark_id", "share_class_id", "lifecycle_status", "eligible_for_research"}
    ids: set[str] = set()
    tickers: set[str] = set()
    for record in records:
        missing = required - set(record)
        if missing:
            raise SecurityMasterValidationError(f"Missing security fields: {sorted(missing)}")
        if not str(record["security_id"]).startswith("SEC-"):
            raise SecurityMasterValidationError("Stable security_id is required")
        if record["security_id"] in ids or record["ticker"] in tickers:
            raise SecurityMasterValidationError("Duplicate identity detected")
        ids.add(record["security_id"])
        tickers.add(record["ticker"])
        if record["lifecycle_status"] not in master.get("lifecycle_states", []):
            raise SecurityMasterValidationError("Unknown lifecycle status")


def validate_registries(master: dict, issuer_funds: dict, benchmarks: dict) -> None:
    issuer_ids = {item["issuer_id"] for item in issuer_funds.get("issuers", [])}
    fund_map = {item["fund_id"]: item["issuer_id"] for item in issuer_funds.get("funds", [])}
    benchmark_ids = {item["benchmark_id"] for item in benchmarks.get("benchmarks", [])}
    if benchmarks.get("unknown_benchmark_blocked") is not True:
        raise SecurityMasterValidationError("Unknown benchmarks must be blocked")
    for security in master["securities"]:
        if security["issuer_id"] not in issuer_ids:
            raise SecurityMasterValidationError("Unknown issuer")
        if fund_map.get(security["fund_id"]) != security["issuer_id"]:
            raise SecurityMasterValidationError("Fund and issuer relationship is invalid")
        if security["benchmark_id"] not in benchmark_ids:
            raise SecurityMasterValidationError("Unknown benchmark")


def eligible_security_ids(master: dict, policy: dict) -> list[str]:
    required = policy.get("security_ids")
    if policy.get("unknown_security_blocked") is not True or not isinstance(required, list):
        raise SecurityMasterValidationError("Universe policy must fail closed")
    by_id = {item["security_id"]: item for item in master["securities"]}
    eligible: list[str] = []
    for security_id in required:
        security = by_id.get(security_id)
        if security is None:
            raise SecurityMasterValidationError(f"Unknown security: {security_id}")
        if security["asset_type"] != policy["required_asset_type"]:
            raise SecurityMasterValidationError("Asset type is ineligible")
        if security["lifecycle_status"] != policy["required_lifecycle_status"]:
            raise SecurityMasterValidationError("Lifecycle status is ineligible")
        if not security["eligible_for_research"]:
            raise SecurityMasterValidationError("Security is not research eligible")
        eligible.append(security_id)
    return eligible
