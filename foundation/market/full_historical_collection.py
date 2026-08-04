from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_candidate_universe(document: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    records = list(document.get("records") or [])
    expected = int(policy["required_candidate_count"])
    if len(records) != expected:
        raise ValueError(f"Expected {expected} candidates but found {len(records)}")
    if document.get("provisional_records_included") is not False:
        raise ValueError("Provisional candidates are not allowed")
    required_state = policy["required_candidate_state"]
    if any(record.get("screen_state") != required_state for record in records):
        raise ValueError("Candidate universe contains a noneligible record")
    ids = [str(record.get("security_id", "")) for record in records]
    if any(not value for value in ids) or len(set(ids)) != expected:
        raise ValueError("Candidate identities are missing or duplicated")
    symbols = {str(record.get("symbol", "")).upper() for record in records}
    missing = set(policy["required_seed_symbols"]) - symbols
    if missing:
        raise ValueError(f"Candidate universe is missing required seeds: {sorted(missing)}")
    return records


def validate_pilot(checkpoint: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    records = list(checkpoint.get("records") or [])
    by_symbol = {str(record.get("symbol", "")).upper(): record for record in records}
    requirements = policy["pilot_review"]
    for symbol in policy["required_seed_symbols"]:
        record = by_symbol.get(symbol)
        if record is None:
            raise ValueError(f"Pilot is missing {symbol}")
        if record.get("collection_status") != requirements["required_seed_status"]:
            raise ValueError(f"Pilot seed {symbol} is not collected")
        if record.get("provider_data_granularity") != requirements["required_provider_granularity"]:
            raise ValueError(f"Pilot seed {symbol} is not daily")
        observations = int(record.get("observation_count") or 0)
        adjusted = int(record.get("adjusted_price_observation_count") or 0)
        if observations < int(requirements["minimum_seed_observations"]):
            raise ValueError(f"Pilot seed {symbol} has insufficient history")
        if requirements["adjusted_price_coverage_must_be_complete"] and adjusted != observations:
            raise ValueError(f"Pilot seed {symbol} has incomplete adjusted-price coverage")
    return {"pilot_status": "PASS", "pilot_records": len(records)}


def index_checkpoint(checkpoint: dict[str, Any], candidate_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    candidate_ids = {str(record["security_id"]) for record in candidate_records}
    indexed: dict[str, dict[str, Any]] = {}
    for record in checkpoint.get("records") or []:
        security_id = str(record.get("security_id", ""))
        if not security_id or security_id not in candidate_ids:
            raise ValueError("Checkpoint contains an unknown identity")
        if security_id in indexed:
            raise ValueError("Checkpoint contains duplicate identities")
        indexed[security_id] = record
    return indexed


def build_completion_attestation(
    *,
    candidate_path: Path,
    checkpoint_path: Path,
    summary_path: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    candidates = validate_candidate_universe(load_json(candidate_path), policy)
    checkpoint = load_json(checkpoint_path)
    indexed = index_checkpoint(checkpoint, candidates)
    expected = int(policy["full_collection"]["expected_record_count"])
    seed_symbols = set(policy["required_seed_symbols"])
    present_symbols = {str(record.get("symbol", "")).upper() for record in indexed.values()}
    all_terminal = all(
        record.get("collection_status") in set(policy["full_collection"]["terminal_statuses"])
        for record in indexed.values()
    )
    complete = len(indexed) == expected and seed_symbols.issubset(present_symbols) and all_terminal
    status_counts: dict[str, int] = {}
    for record in indexed.values():
        status = str(record.get("collection_status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    attestation = {
        "phase": "3.3",
        "completion_status": policy["completion_states"]["complete"] if complete else policy["completion_states"]["partial"],
        "expected_records": expected,
        "completed_records": len(indexed),
        "remaining_records": expected - len(indexed),
        "unique_security_ids": len(indexed),
        "required_seeds_present": seed_symbols.issubset(present_symbols),
        "all_records_terminal": all_terminal,
        "status_counts": dict(sorted(status_counts.items())),
        "candidate_universe_sha256": sha256_file(candidate_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "summary_sha256": sha256_file(summary_path),
        "authority": policy["authority"],
    }
    return attestation
