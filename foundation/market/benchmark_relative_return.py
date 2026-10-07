from __future__ import annotations

from typing import Any


def compare_horizon(
    *,
    asset_result: dict[str, Any],
    benchmark_result: dict[str, Any],
    horizon: str,
    required_return_basis: str,
) -> dict[str, Any]:
    if asset_result.get("calculation_state") != "CALCULATED":
        return {"horizon": horizon, "comparison_state": "RELATIVE_RETURN_NOT_AUTHORIZED", "reason": "ASSET_RETURN_NOT_CALCULATED"}
    if benchmark_result.get("calculation_state") != "CALCULATED":
        return {"horizon": horizon, "comparison_state": "RELATIVE_RETURN_NOT_AUTHORIZED", "reason": "BENCHMARK_RETURN_NOT_CALCULATED"}
    if asset_result.get("return_basis") != required_return_basis or benchmark_result.get("return_basis") != required_return_basis:
        return {"horizon": horizon, "comparison_state": "RELATIVE_RETURN_BLOCKED", "reason": "RETURN_BASIS_MISMATCH"}
    if asset_result.get("start_date") != benchmark_result.get("start_date"):
        return {"horizon": horizon, "comparison_state": "RELATIVE_RETURN_BLOCKED", "reason": "START_DATE_MISMATCH"}
    if asset_result.get("end_date") != benchmark_result.get("end_date"):
        return {"horizon": horizon, "comparison_state": "RELATIVE_RETURN_BLOCKED", "reason": "END_DATE_MISMATCH"}
    asset_return = asset_result.get("cumulative_total_return")
    benchmark_return = benchmark_result.get("cumulative_total_return")
    if not isinstance(asset_return, (int, float)) or not isinstance(benchmark_return, (int, float)):
        return {"horizon": horizon, "comparison_state": "RELATIVE_RETURN_BLOCKED", "reason": "RETURN_VALUE_MISSING"}
    return {
        "horizon": horizon,
        "comparison_state": "RELATIVE_RETURN_CALCULATED",
        "return_basis": required_return_basis,
        "start_date": asset_result["start_date"],
        "end_date": asset_result["end_date"],
        "asset_cumulative_total_return": float(asset_return),
        "benchmark_cumulative_total_return": float(benchmark_return),
        "excess_total_return": float(asset_return) - float(benchmark_return),
    }


def compare_record(
    asset_record: dict[str, Any],
    *,
    benchmark_record: dict[str, Any] | None,
    assignment: dict[str, Any] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    security_id = str(asset_record.get("security_id") or "")
    symbol = str(asset_record.get("symbol") or "").upper()
    horizons = policy["uip_horizon_contract"]
    blocked_authority = {
        "risk_analytics": False,
        "forecasting": False,
        "ranking": False,
        "recommendations": False,
        "portfolio_allocation": False,
        "uip_export": False,
        "automatic_execution": False,
    }
    if assignment is None:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "benchmark_state": "BENCHMARK_UNASSIGNED",
            "comparison_reasons": ["BENCHMARK_ASSIGNMENT_MISSING"],
            "horizons": {h: {"horizon": h, "comparison_state": "RELATIVE_RETURN_NOT_AUTHORIZED", "reason": "BENCHMARK_UNASSIGNED"} for h in horizons},
            "authority": {"relative_return_calculation": False, **blocked_authority},
        }
    benchmark_id = str(assignment.get("benchmark_security_id") or "")
    benchmark_class = str(assignment.get("benchmark_class") or "UNASSIGNED")
    taxonomy_evidence = assignment.get("taxonomy_evidence")
    if not benchmark_id or not taxonomy_evidence:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "benchmark_state": "BENCHMARK_BLOCKED",
            "benchmark_security_id": benchmark_id or None,
            "benchmark_class": benchmark_class,
            "comparison_reasons": ["BENCHMARK_IDENTITY_OR_TAXONOMY_EVIDENCE_MISSING"],
            "horizons": {h: {"horizon": h, "comparison_state": "RELATIVE_RETURN_BLOCKED", "reason": "BENCHMARK_ASSIGNMENT_INVALID"} for h in horizons},
            "authority": {"relative_return_calculation": False, **blocked_authority},
        }
    if benchmark_id == security_id:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "benchmark_state": "BENCHMARK_BLOCKED",
            "benchmark_security_id": benchmark_id,
            "benchmark_class": benchmark_class,
            "comparison_reasons": ["SELF_BENCHMARK_COMPARISON_PROHIBITED"],
            "horizons": {h: {"horizon": h, "comparison_state": "RELATIVE_RETURN_BLOCKED", "reason": "SELF_BENCHMARK_COMPARISON_PROHIBITED"} for h in horizons},
            "authority": {"relative_return_calculation": False, **blocked_authority},
        }
    if benchmark_record is None:
        return {
            "security_id": security_id,
            "symbol": symbol,
            "benchmark_state": "BENCHMARK_UNSUPPORTED",
            "benchmark_security_id": benchmark_id,
            "benchmark_class": benchmark_class,
            "comparison_reasons": ["BENCHMARK_RETURN_RECORD_MISSING"],
            "horizons": {h: {"horizon": h, "comparison_state": "RELATIVE_RETURN_NOT_AUTHORIZED", "reason": "BENCHMARK_UNSUPPORTED"} for h in horizons},
            "authority": {"relative_return_calculation": False, **blocked_authority},
        }
    results = {
        horizon: compare_horizon(
            asset_result=(asset_record.get("horizons") or {}).get(horizon) or {},
            benchmark_result=(benchmark_record.get("horizons") or {}).get(horizon) or {},
            horizon=horizon,
            required_return_basis=policy["required_return_basis"],
        )
        for horizon in horizons
    }
    authorized = any(item["comparison_state"] == "RELATIVE_RETURN_CALCULATED" for item in results.values())
    return {
        "security_id": security_id,
        "symbol": symbol,
        "benchmark_state": "BENCHMARK_ASSIGNED",
        "benchmark_security_id": benchmark_id,
        "benchmark_symbol": benchmark_record.get("symbol"),
        "benchmark_class": benchmark_class,
        "taxonomy_evidence": taxonomy_evidence,
        "horizons": results,
        "authority": {"relative_return_calculation": authorized, **blocked_authority},
    }
