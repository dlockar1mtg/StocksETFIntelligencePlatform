from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SECURITY_ID = re.compile(r"^SEC-[A-Z0-9-]{6,64}$")


class ContractValidationError(ValueError):
    """Raised when governed contract or configuration validation fails."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"Unable to load valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ContractValidationError(f"Expected object at root: {path}")
    return data


def major(version: str) -> int:
    if not SEMVER.fullmatch(version):
        raise ContractValidationError(f"Invalid semantic version: {version}")
    return int(version.split(".", 1)[0])


def versions_compatible(expected: str, actual: str) -> bool:
    return major(expected) == major(actual)


def validate_contract_registry(registry: dict[str, Any]) -> None:
    required = {"registry_version", "compatibility_policy", "breaking_changes_require_migration", "unknown_contracts_blocked", "contracts"}
    if not required.issubset(registry):
        raise ContractValidationError("Contract registry is missing required controls")
    if registry["compatibility_policy"] != "major_version_must_match":
        raise ContractValidationError("Unsupported compatibility policy")
    if registry["breaking_changes_require_migration"] is not True or registry["unknown_contracts_blocked"] is not True:
        raise ContractValidationError("Contract registry must fail closed")
    seen: set[str] = set()
    for item in registry["contracts"]:
        contract_id = item.get("contract_id")
        if not contract_id or contract_id in seen:
            raise ContractValidationError("Contract IDs must be unique and non-empty")
        seen.add(contract_id)
        major(item.get("version", ""))
        if item.get("status") != "ACTIVE":
            raise ContractValidationError("Only ACTIVE contracts may be used in Phase 0.3")


def validate_security_identity(record: dict[str, Any]) -> None:
    required = {"security_id", "asset_type", "ticker", "exchange", "currency", "identity_status"}
    if not required.issubset(record):
        raise ContractValidationError("Security identity is missing required fields")
    if not SECURITY_ID.fullmatch(str(record["security_id"])):
        raise ContractValidationError("Invalid stable security_id")
    if record["asset_type"] not in {"ETF", "EQUITY"}:
        raise ContractValidationError("Invalid asset_type")
    if record["identity_status"] not in {"PROVISIONAL", "CERTIFIED", "CONFLICTED", "RETIRED"}:
        raise ContractValidationError("Invalid identity_status")
    if not re.fullmatch(r"[A-Z]{3}", str(record["currency"])):
        raise ContractValidationError("Invalid currency")


def validate_initial_universe(config: dict[str, Any]) -> None:
    if config.get("scope") != "ETF_ONLY":
        raise ContractValidationError("Initial universe must remain ETF_ONLY")
    if config.get("individual_stock_production_authorized") is not False:
        raise ContractValidationError("Individual-stock production must remain unauthorized")
    securities = config.get("securities")
    if not isinstance(securities, list):
        raise ContractValidationError("Securities must be a list")
    tickers = [item.get("ticker") for item in securities]
    if tickers != ["VOO", "SCHD", "QQQM"]:
        raise ContractValidationError("Initial ETF scope must remain VOO, SCHD, QQQM in governed order")
    ids = [item.get("security_id") for item in securities]
    if len(ids) != len(set(ids)) or any(not SECURITY_ID.fullmatch(str(value)) for value in ids):
        raise ContractValidationError("Stable security IDs must be unique and valid")
