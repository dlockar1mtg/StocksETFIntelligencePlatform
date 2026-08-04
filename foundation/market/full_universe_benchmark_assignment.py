from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from foundation.market.benchmark_assignment_registry import assign_benchmark


class FullUniverseBenchmarkAssignmentError(ValueError):
    """Raised when Phase 3.6b evidence fails closed."""


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        for key in ("records", "taxonomy_records", "assignments"):
            value = document.get(key)
            if isinstance(value, list):
                return value
    raise FullUniverseBenchmarkAssignmentError("INPUT_RECORD_ARRAY_MISSING")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_full_universe_assignment(
    taxonomy_document: Any,
    return_document: Any,
    policy: dict[str, Any],
    registry_policy: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    taxonomy_records = _records(taxonomy_document)
    return_records = _records(return_document)
    required = int(policy["required_record_count"])
    if len(taxonomy_records) != required or len(return_records) != required:
        raise FullUniverseBenchmarkAssignmentError("REQUIRED_RECORD_COUNT_MISMATCH")

    taxonomy_by_id: dict[str, dict[str, Any]] = {}
    for record in taxonomy_records:
        security_id = record.get("security_id")
        if not security_id:
            raise FullUniverseBenchmarkAssignmentError("STABLE_SECURITY_ID_MISSING")
        if security_id in taxonomy_by_id:
            raise FullUniverseBenchmarkAssignmentError("DUPLICATE_TAXONOMY_SECURITY_ID")
        taxonomy_by_id[security_id] = record

    returns_by_id: dict[str, dict[str, Any]] = {}
    for record in return_records:
        security_id = record.get("security_id")
        if not security_id:
            raise FullUniverseBenchmarkAssignmentError("RETURN_SECURITY_ID_MISSING")
        if security_id in returns_by_id:
            raise FullUniverseBenchmarkAssignmentError("DUPLICATE_RETURN_SECURITY_ID")
        returns_by_id[security_id] = record

    if set(taxonomy_by_id) != set(returns_by_id):
        raise FullUniverseBenchmarkAssignmentError("TAXONOMY_RETURN_IDENTITY_MISMATCH")

    assignments: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    taxonomy_coverage: dict[str, Counter[str]] = defaultdict(Counter)
    active_candidates: list[dict[str, Any]] = []

    for security_id in sorted(taxonomy_by_id):
        taxonomy = taxonomy_by_id[security_id]
        returns = returns_by_id[security_id]
        assignment = assign_benchmark(taxonomy, registry_policy, rules)
        state = assignment["assignment_state"]
        reasons = list(assignment.get("assignment_reasons") or [])
        return_state = returns.get("calculation_state")
        active = state == "BENCHMARK_ASSIGNED" and return_state == "CALCULATED"

        output = {
            "security_id": security_id,
            "symbol": returns.get("symbol") or taxonomy.get("symbol"),
            "assignment_state": state,
            "assignment_reasons": reasons,
            "benchmark_class": assignment.get("benchmark_class"),
            "benchmark_security_id": assignment.get("benchmark_security_id"),
            "benchmark_symbol": assignment.get("benchmark_symbol"),
            "taxonomy": {
                key: taxonomy.get(key)
                for key in (
                    "asset_class", "strategy", "geography", "market_segment",
                    "income_profile", "implementation", "specialized_product_type",
                    "portfolio_treatment", "classification_status", "source_id",
                    "source_record_id", "content_sha256"
                )
            },
            "return_calculation_state": return_state,
            "return_output_sha256": returns.get("source_lineage", {}).get("total_return_output_sha256"),
            "active_analytical_candidate": active,
            "processing_treatment": "ADVANCE" if active else "PRESERVE_EXCLUDE",
        }
        assignments.append(output)
        state_counts[state] += 1
        for reason in reasons:
            reason_counts[reason] += 1
        if output["benchmark_class"]:
            class_counts[output["benchmark_class"]] += 1
        for dimension in ("asset_class", "strategy", "geography", "market_segment", "specialized_product_type"):
            taxonomy_coverage[dimension][str(taxonomy.get(dimension, "MISSING"))] += 1
        if active:
            active_candidates.append({
                "security_id": security_id,
                "symbol": output["symbol"],
                "benchmark_class": output["benchmark_class"],
                "benchmark_security_id": output["benchmark_security_id"],
            })

    if sum(state_counts.values()) != required:
        raise FullUniverseBenchmarkAssignmentError("ASSIGNMENT_STATE_RECONCILIATION_FAILED")

    return {
        "phase": "3.6b",
        "record_count": required,
        "assignment_state_counts": dict(sorted(state_counts.items())),
        "assignment_reason_counts": dict(sorted(reason_counts.items())),
        "benchmark_class_counts": dict(sorted(class_counts.items())),
        "taxonomy_dimension_counts": {
            key: dict(sorted(value.items())) for key, value in sorted(taxonomy_coverage.items())
        },
        "active_analytical_candidate_count": len(active_candidates),
        "excluded_preserved_count": required - len(active_candidates),
        "assignments": assignments,
        "active_analytical_candidates": active_candidates,
        "authority": policy["authority"],
    }


def write_outputs(result: dict[str, Any], output: Path, summary: Path, candidates: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    candidates.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_payload = {key: value for key, value in result.items() if key not in {"assignments", "active_analytical_candidates"}}
    summary_payload["assignment_output_sha256"] = _sha256(output)
    summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    candidates.write_text(json.dumps({
        "phase": "3.6b",
        "publication_status": "REVIEW_ONLY_NOT_CERTIFIED",
        "record_count": result["active_analytical_candidate_count"],
        "records": result["active_analytical_candidates"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
