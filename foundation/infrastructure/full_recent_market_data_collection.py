from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


class FullCollectionValidationError(ValueError):
    pass


def load_records(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = list(document.get("records") or [])
    if not records:
        raise FullCollectionValidationError("Active-universe input contains no records.")
    return records


def index_records(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        security_id = str(record.get("security_id") or "").strip()
        symbol = str(record.get("symbol") or "").strip().upper()
        if not security_id or not symbol:
            raise FullCollectionValidationError("Every record requires security_id and symbol.")
        if security_id in indexed:
            raise FullCollectionValidationError(f"Duplicate security_id: {security_id}")
        indexed[security_id] = {**record, "symbol": symbol}
    return indexed


def validate_input(records: list[dict[str, Any]], policy: dict[str, Any]) -> None:
    indexed = index_records(records)
    expected = int(policy["expected_input_record_count"])
    if len(indexed) != expected:
        raise FullCollectionValidationError(
            f"Expected {expected} active records but found {len(indexed)}."
        )
    symbols = {record["symbol"] for record in indexed.values()}
    missing = [symbol for symbol in policy["required_seed_symbols"] if symbol not in symbols]
    if missing:
        raise FullCollectionValidationError(f"Missing required seeds: {', '.join(missing)}")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise FullCollectionValidationError("Selection principle drifted.")
    if policy.get("target_universe_size") is not None:
        raise FullCollectionValidationError("Arbitrary target universe size is prohibited.")
    if policy.get("preserve_all_input_records") is not True:
        raise FullCollectionValidationError("All input records must be preserved.")
    if policy.get("destructive_deletion_allowed") is not False:
        raise FullCollectionValidationError("Destructive deletion must remain disabled.")
    if any(bool(value) for value in policy["authority"].values()):
        raise FullCollectionValidationError("Phase 2B.3 cannot grant downstream authority.")


def merge_checkpoint(
    input_records: list[dict[str, Any]],
    checkpoint_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    input_index = index_records(input_records)
    checkpoint_index: dict[str, dict[str, Any]] = {}
    for record in checkpoint_records:
        security_id = str(record.get("security_id") or "").strip()
        if security_id not in input_index:
            raise FullCollectionValidationError(
                f"Checkpoint contains unknown security_id: {security_id}"
            )
        checkpoint_index[security_id] = record
    return checkpoint_index


def pending_records(
    input_records: list[dict[str, Any]],
    checkpoint_records: list[dict[str, Any]],
    *,
    retry_failed: bool,
    retryable_statuses: set[str],
) -> list[dict[str, Any]]:
    checkpoint_index = merge_checkpoint(input_records, checkpoint_records)
    pending: list[dict[str, Any]] = []
    for record in input_records:
        prior = checkpoint_index.get(record["security_id"])
        if prior is None:
            pending.append(record)
            continue
        if retry_failed and prior.get("collection_status") in retryable_statuses:
            pending.append(record)
    return pending


def replace_checkpoint_record(
    checkpoint_records: list[dict[str, Any]], new_record: dict[str, Any]
) -> list[dict[str, Any]]:
    security_id = new_record["security_id"]
    output = [record for record in checkpoint_records if record.get("security_id") != security_id]
    output.append(new_record)
    output.sort(key=lambda record: record["security_id"])
    return output


def build_completion_summary(
    input_records: list[dict[str, Any]],
    checkpoint_records: list[dict[str, Any]],
    policy: dict[str, Any],
    operating_date: str,
) -> dict[str, Any]:
    checkpoint_index = merge_checkpoint(input_records, checkpoint_records)
    statuses = Counter(
        str(record.get("collection_status") or "UNKNOWN")
        for record in checkpoint_index.values()
    )
    input_symbols = {record["symbol"] for record in input_records}
    completed_symbols = {
        str(record.get("symbol") or "").upper() for record in checkpoint_index.values()
    }
    missing_seeds = [
        symbol for symbol in policy["required_seed_symbols"]
        if symbol not in input_symbols or symbol not in completed_symbols
    ]
    complete = len(checkpoint_index) == len(input_records) and not missing_seeds
    return {
        "phase": "2B.3",
        "operating_date": operating_date,
        "input_records": len(input_records),
        "completed_unique_records": len(checkpoint_index),
        "remaining_records": len(input_records) - len(checkpoint_index),
        "status_counts": dict(sorted(statuses.items())),
        "required_seed_symbols": policy["required_seed_symbols"],
        "missing_seed_symbols": missing_seeds,
        "preserve_all_input_records": policy["preserve_all_input_records"],
        "selection_principle": policy["selection_principle"],
        "target_universe_size": policy["target_universe_size"],
        "collection_complete": complete,
        "authority": policy["authority"],
    }
