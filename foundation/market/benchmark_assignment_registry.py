from __future__ import annotations

from collections import Counter

ASSIGNED = "BENCHMARK_ASSIGNED"
UNASSIGNED = "BENCHMARK_UNASSIGNED"
UNSUPPORTED = "BENCHMARK_UNSUPPORTED"
CONFLICTED = "BENCHMARK_CONFLICTED"


def assign_benchmark(record: dict, registry: dict, policy: dict) -> dict:
    security_id = record.get("security_id")
    symbol = record.get("symbol")
    status = record.get("classification_status")
    specialized = record.get("specialized_product_type", "NONE")
    reasons: list[str] = []

    result = {
        "security_id": security_id,
        "symbol": symbol,
        "assignment_state": UNASSIGNED,
        "assignment_reasons": reasons,
        "benchmark_class": None,
        "benchmark_security_id": None,
        "benchmark_symbol": None,
        "taxonomy_lineage": {
            "source_id": record.get("source_id"),
            "source_record_id": record.get("source_record_id"),
            "content_sha256": record.get("content_sha256"),
        },
        "authority": {"relative_return_calculation": False},
    }

    if not security_id:
        raise ValueError("MISSING_SECURITY_ID")
    if status in {"CONFLICTED", "QUARANTINED"}:
        result["assignment_state"] = CONFLICTED
        reasons.append("TAXONOMY_CONFLICTED")
        return result
    if status != "CLASSIFIED":
        reasons.append("TAXONOMY_NOT_CLASSIFIED")
        return result
    if specialized in set(policy["unsupported_specialized_product_types"]):
        result["assignment_state"] = UNSUPPORTED
        reasons.append("SPECIALIZED_PRODUCT_UNSUPPORTED")
        return result

    key = "|".join([
        str(record.get("asset_class", "")),
        str(record.get("strategy", "")),
        str(record.get("geography", "")),
        str(record.get("market_segment", "")),
    ])
    candidates = registry.get("assignments", {}).get(key, [])
    if len(candidates) == 0:
        reasons.append("NO_SUPPORTED_BENCHMARK_RULE")
        return result
    if len(candidates) > 1:
        result["assignment_state"] = CONFLICTED
        reasons.append("MULTIPLE_BENCHMARK_RULES")
        return result

    candidate = candidates[0]
    benchmark_security_id = candidate.get("benchmark_security_id")
    if not benchmark_security_id:
        raise ValueError("MISSING_BENCHMARK_SECURITY_ID")
    if benchmark_security_id == security_id:
        result["assignment_state"] = CONFLICTED
        reasons.append("SELF_BENCHMARK_ASSIGNMENT")
        return result

    result.update({
        "assignment_state": ASSIGNED,
        "benchmark_class": candidate.get("benchmark_class"),
        "benchmark_security_id": benchmark_security_id,
        "benchmark_symbol": candidate.get("benchmark_symbol"),
    })
    return result


def build_assignment_registry(records: list[dict], registry: dict, policy: dict) -> dict:
    required = int(policy["required_record_count"])
    if len(records) != required:
        raise ValueError("RECORD_COUNT_MISMATCH")
    identities = [item.get("security_id") for item in records]
    if None in identities or len(set(identities)) != required:
        raise ValueError("DUPLICATE_OR_MISSING_SECURITY_ID")
    assignments = [assign_benchmark(item, registry, policy) for item in records]
    counts = Counter(item["assignment_state"] for item in assignments)
    return {
        "phase": "3.6a",
        "record_count": len(assignments),
        "assignment_state_counts": dict(sorted(counts.items())),
        "records": assignments,
        "authority": policy["authority"],
    }
