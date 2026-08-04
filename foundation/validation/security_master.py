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
    required = {
        "security_id", "ticker", "asset_type", "issuer_id", "fund_id",
        "exchange", "currency", "benchmark_id", "share_class_id",
        "lifecycle_status", "eligible_for_research",
    }
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


def validate_universe_policy(policy: dict) -> None:
    if policy.get("fail_closed") is not True:
        raise SecurityMasterValidationError("Universe policy must fail closed")
    if policy.get("unknown_security_blocked") is not True:
        raise SecurityMasterValidationError("Unknown securities must be blocked")
    seeds = policy.get("seed_security_ids")
    if not isinstance(seeds, list) or not seeds:
        raise SecurityMasterValidationError("Seed securities are required")
    if len(seeds) != len(set(seeds)):
        raise SecurityMasterValidationError("Duplicate seed security detected")
    requirements = policy.get("admission_requirements")
    if not isinstance(requirements, dict):
        raise SecurityMasterValidationError("Admission requirements are required")
    required_true = {
        "stable_security_id",
        "complete_identity",
        "authoritative_listing_evidence",
        "broker_eligibility_evidence",
        "broker_verification_timestamp",
    }
    for key in required_true:
        if requirements.get(key) is not True:
            raise SecurityMasterValidationError(f"Admission requirement weakened: {key}")
    if requirements.get("broker_status_unknown_is_eligible") is not False:
        raise SecurityMasterValidationError("Unknown broker status cannot be eligible")
    if requirements.get("ticker_as_sole_identifier_allowed") is not False:
        raise SecurityMasterValidationError("Ticker-only identity cannot be allowed")


def eligible_security_ids(master: dict, policy: dict) -> list[str]:
    validate_universe_policy(policy)
    by_id = {item["security_id"]: item for item in master["securities"]}
    seeds = policy["seed_security_ids"]
    for security_id in seeds:
        if security_id not in by_id:
            raise SecurityMasterValidationError(f"Missing seed security: {security_id}")

    eligible: list[str] = []
    for security in master["securities"]:
        if security["asset_type"] != policy["required_asset_type"]:
            continue
        if security["lifecycle_status"] != policy["required_lifecycle_status"]:
            continue
        if not security["eligible_for_research"]:
            continue
        eligible.append(security["security_id"])

    missing_seeds = sorted(set(seeds) - set(eligible))
    if missing_seeds:
        raise SecurityMasterValidationError(
            f"Seed securities are not eligible: {missing_seeds}"
        )
    return eligible
