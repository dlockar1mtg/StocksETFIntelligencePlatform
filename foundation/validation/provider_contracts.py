from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProviderContractError(ValueError):
    """Raised when a provider contract or observation violates governance."""


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SECURITY_ID_PATTERN = re.compile(r"^SEC-[A-Z]{2}-[A-Z0-9.-]+$")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderContractError(f"Unable to load governed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ProviderContractError(f"Governed JSON must be an object: {path}")
    return value


def validate_provider_control(control: dict[str, Any]) -> None:
    if control.get("phase") != "1.1" or control.get("fail_closed") is not True:
        raise ProviderContractError("Provider control must be fail-closed for Phase 1.1")
    required_domains = {
        "raw_price", "adjusted_price", "distribution", "corporate_action",
        "etf_metadata", "holdings", "expense_ratio", "assets_under_management",
        "liquidity", "benchmark",
    }
    if set(control.get("governed_domains", [])) != required_domains:
        raise ProviderContractError("Governed provider domains are incomplete")
    for flag in (
        "unknown_providers_blocked", "undeclared_domains_blocked",
        "secrets_must_remain_outside_git", "raw_payloads_must_remain_outside_git",
        "conflicting_observations_must_be_preserved", "critical_conflicts_must_be_quarantined",
        "missing_required_fields_block_observation", "future_observations_blocked",
        "ticker_only_identity_blocked", "provider_adjusted_values_require_reconciliation",
    ):
        if control.get(flag) is not True:
            raise ProviderContractError(f"Required provider safeguard disabled: {flag}")
    for flag in (
        "direct_uip_database_writes_authorized",
        "certified_market_monitoring_authorized",
        "certified_analytics_authorized",
    ):
        if control.get(flag) is not False:
            raise ProviderContractError(f"Unauthorized Phase 1 authority enabled: {flag}")


def validate_observation(control: dict[str, Any], observation: dict[str, Any], *, now: datetime | None = None) -> None:
    required = set(control["required_provider_fields"]) | set(control["required_observation_fields"]) | {"payload"}
    missing = sorted(required - observation.keys())
    if missing:
        raise ProviderContractError(f"Missing required observation fields: {missing}")
    if observation["domain"] not in control["governed_domains"]:
        raise ProviderContractError("Observation domain is not governed")
    if observation["source_tier"] not in control["allowed_source_tiers"]:
        raise ProviderContractError("Invalid source tier")
    if observation["quality_status"] not in control["allowed_quality_states"]:
        raise ProviderContractError("Invalid quality status")
    if observation["freshness_state"] not in control["allowed_freshness_states"]:
        raise ProviderContractError("Invalid freshness state")
    if not SECURITY_ID_PATTERN.fullmatch(observation["security_id"]):
        raise ProviderContractError("Stable security identity is required")
    if not SHA256_PATTERN.fullmatch(observation["content_sha256"]):
        raise ProviderContractError("Invalid content SHA-256")
    observed = datetime.fromisoformat(observation["observed_at_utc"].replace("Z", "+00:00"))
    retrieved = datetime.fromisoformat(observation["retrieved_at_utc"].replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if observed > current or retrieved > current or retrieved < observed:
        raise ProviderContractError("Observation timestamps violate point-in-time ordering")
    if not isinstance(observation["payload"], dict):
        raise ProviderContractError("Observation payload must be an object")


def validate_phase_1_1(root: Path) -> dict[str, Any]:
    control = load_json(root / "config/providers/provider_contracts.json")
    validate_provider_control(control)
    schema = load_json(root / "contracts/native/provider_observation.schema.json")
    if schema.get("additionalProperties") is not False:
        raise ProviderContractError("Provider observation schema must reject unknown fields")
    return control
