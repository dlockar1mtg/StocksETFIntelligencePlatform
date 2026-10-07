from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OPERATING_DATE = "2026-08-06"
REFERENCE_COUNT = 3462
MODEL_COUNT = 1077
MINIMUM_MEDIAN_DOLLAR_VOLUME_USD = 1_000_000.0
REQUIRED_SEEDS = {"VOO", "SCHD", "QQQM"}

MARKET_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "market_data_foundation"
    / "2026-08-03"
    / "phase_3_market_data_candidate_universe.json"
)

CERTIFICATION_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "historical_evidence_certification"
    / "2026-08-04"
    / "historical_evidence_certification.json"
)

RETURNS_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "total_returns"
    / "2026-08-04"
    / "total_return_calculations.json"
)

ISSUER_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "staged"
    / "issuer_identity_ledger_rebuild"
    / "2026-08-04"
    / "issuer_identity_ledger.json"
)

POLICY_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "market"
    / "etf_model_universe_certification_policy.json"
)

OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "data"
    / "certified"
    / "etf_model_universe"
    / OPERATING_DATE
)

MODEL_UNIVERSE_PATH = (
    OUTPUT_DIRECTORY / "phase_3_etf_model_universe.json"
)

DECISION_LEDGER_PATH = (
    OUTPUT_DIRECTORY / "phase_3_etf_model_universe_decision_ledger.json"
)

CERTIFICATION_PATH_OUT = (
    OUTPUT_DIRECTORY / "phase_3_etf_model_universe_certification.json"
)


class CertificationError(RuntimeError):
    """Raised when governed model-universe certification fails."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CertificationError(f"Missing required source: {path}")

    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise CertificationError(f"Expected JSON object in {path}")

    return value


def index_records(
    document: dict[str, Any],
    source_name: str,
) -> dict[str, dict[str, Any]]:
    records = document.get("records")

    if not isinstance(records, list):
        raise CertificationError(
            f"{source_name} does not contain a records list."
        )

    if len(records) != REFERENCE_COUNT:
        raise CertificationError(
            f"{source_name} expected {REFERENCE_COUNT} records; "
            f"found {len(records)}."
        )

    result: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            raise CertificationError(
                f"{source_name} contains a non-object record."
            )

        security_id = record.get("security_id")

        if not isinstance(security_id, str) or not security_id:
            raise CertificationError(
                f"{source_name} contains a missing security_id."
            )

        if security_id in result:
            raise CertificationError(
                f"{source_name} contains duplicate security_id "
                f"{security_id!r}."
            )

        result[security_id] = record

    return result


def read_horizon_eligibility(
    record: dict[str, Any],
    horizon: str,
) -> bool:
    horizons = record.get("eligible_horizons")

    if not isinstance(horizons, dict):
        return False

    return horizons.get(horizon) is True


def read_float(
    value: Any,
    field_name: str,
    security_id: str,
) -> float:
    if isinstance(value, bool):
        raise CertificationError(
            f"{security_id}: invalid Boolean for {field_name}."
        )

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise CertificationError(
            f"{security_id}: invalid {field_name}: {value!r}"
        ) from exc

    return parsed


def build_decision(
    security_id: str,
    market: dict[str, Any],
    certification: dict[str, Any],
    returns: dict[str, Any],
    issuer: dict[str, Any],
) -> dict[str, Any]:
    symbol = market.get("symbol")

    if not isinstance(symbol, str) or not symbol:
        raise CertificationError(
            f"{security_id}: missing market symbol."
        )

    cross_source_symbols = {
        str(record.get("symbol"))
        for record in (market, certification, returns, issuer)
    }

    if cross_source_symbols != {symbol}:
        raise CertificationError(
            f"{security_id}: symbol mismatch across sources: "
            f"{sorted(cross_source_symbols)}"
        )

    median_dollar_volume = read_float(
        market.get("median_daily_dollar_volume_usd"),
        "median_daily_dollar_volume_usd",
        security_id,
    )

    five_year_eligible = read_horizon_eligibility(
        certification,
        "5y",
    )

    conditions = {
        "market_data_eligible": (
            market.get("screen_state") == "MARKET_DATA_ELIGIBLE"
        ),
        "five_year_eligible": five_year_eligible,
        "minimum_liquidity_met": (
            median_dollar_volume
            >= MINIMUM_MEDIAN_DOLLAR_VOLUME_USD
        ),
        "returns_calculated": (
            returns.get("calculation_state") == "CALCULATED"
        ),
        "issuer_identity_allowed": (
            issuer.get("issuer_identity_state")
            in {"ISSUER_CONFIRMED", "PILOT_COMPLETE"}
        ),
    }

    included = all(conditions.values())

    exclusion_reasons = [
        name
        for name, passed in conditions.items()
        if not passed
    ]

    return {
        "security_id": security_id,
        "symbol": symbol,
        "model_included": included,
        "model_state": (
            "ETF_MODEL_INCLUDED"
            if included
            else "ETF_REFERENCE_ONLY"
        ),
        "inclusion_conditions": conditions,
        "exclusion_reasons": exclusion_reasons,
        "evidence": {
            "market_screen_state": market.get("screen_state"),
            "historical_evidence_state": certification.get(
                "evidence_state"
            ),
            "five_year_eligible": five_year_eligible,
            "observation_count": certification.get(
                "observation_count"
            ),
            "median_daily_dollar_volume_usd": (
                median_dollar_volume
            ),
            "return_calculation_state": returns.get(
                "calculation_state"
            ),
            "issuer_identity_state": issuer.get(
                "issuer_identity_state"
            ),
            "issuer_name": issuer.get("issuer_name"),
            "issuer_cik": issuer.get("issuer_cik"),
        },
        "downstream_authority": {
            "taxonomy_development_authorized": included,
            "benchmark_assignment_authorized": False,
            "risk_model_authorized": False,
            "ranking_authorized": False,
            "forecasting_authorized": False,
            "recommendations_authorized": False,
            "allocation_authorized": False,
            "automatic_execution_authorized": False,
            "uip_database_write_authorized": False,
        },
    }


def main() -> None:
    policy = load_json(POLICY_PATH)
    market_document = load_json(MARKET_PATH)
    certification_document = load_json(CERTIFICATION_PATH)
    returns_document = load_json(RETURNS_PATH)
    issuer_document = load_json(ISSUER_PATH)

    market_index = index_records(
        market_document,
        "market universe",
    )
    certification_index = index_records(
        certification_document,
        "historical certification",
    )
    returns_index = index_records(
        returns_document,
        "total returns",
    )
    issuer_index = index_records(
        issuer_document,
        "issuer identity",
    )

    reference_ids = set(market_index)

    for source_name, source_index in (
        ("historical certification", certification_index),
        ("total returns", returns_index),
        ("issuer identity", issuer_index),
    ):
        if set(source_index) != reference_ids:
            missing = sorted(reference_ids - set(source_index))
            extra = sorted(set(source_index) - reference_ids)

            raise CertificationError(
                f"{source_name} population mismatch. "
                f"Missing={missing[:10]}, extra={extra[:10]}"
            )

    decisions = [
        build_decision(
            security_id=security_id,
            market=market_index[security_id],
            certification=certification_index[security_id],
            returns=returns_index[security_id],
            issuer=issuer_index[security_id],
        )
        for security_id in sorted(reference_ids)
    ]

    included_decisions = [
        decision
        for decision in decisions
        if decision["model_included"]
    ]

    excluded_decisions = [
        decision
        for decision in decisions
        if not decision["model_included"]
    ]

    if len(decisions) != REFERENCE_COUNT:
        raise CertificationError(
            f"Decision ledger expected {REFERENCE_COUNT}; "
            f"found {len(decisions)}."
        )

    if len(included_decisions) != MODEL_COUNT:
        raise CertificationError(
            f"Model universe expected {MODEL_COUNT}; "
            f"found {len(included_decisions)}."
        )

    included_symbols = {
        decision["symbol"]
        for decision in included_decisions
    }

    missing_seeds = sorted(REQUIRED_SEEDS - included_symbols)

    if missing_seeds:
        raise CertificationError(
            f"Required seeds missing from model universe: "
            f"{missing_seeds}"
        )

    duplicate_symbols = [
        symbol
        for symbol, count in Counter(
            decision["symbol"]
            for decision in included_decisions
        ).items()
        if count > 1
    ]

    if duplicate_symbols:
        raise CertificationError(
            f"Duplicate included symbols detected: "
            f"{sorted(duplicate_symbols)}"
        )

    source_hashes = {
        "policy_sha256": sha256_file(POLICY_PATH),
        "market_universe_sha256": sha256_file(MARKET_PATH),
        "historical_certification_sha256": sha256_file(
            CERTIFICATION_PATH
        ),
        "total_returns_sha256": sha256_file(RETURNS_PATH),
        "issuer_identity_sha256": sha256_file(ISSUER_PATH),
    }

    decision_ledger = {
        "artifact_id": (
            "PHASE_3_ETF_MODEL_UNIVERSE_DECISION_LEDGER"
        ),
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "reference_population_count": len(decisions),
        "included_model_population_count": len(
            included_decisions
        ),
        "excluded_reference_population_count": len(
            excluded_decisions
        ),
        "source_hashes": source_hashes,
        "records": decisions,
    }

    model_records = [
        {
            "security_id": decision["security_id"],
            "symbol": decision["symbol"],
            "model_state": decision["model_state"],
            "inclusion_conditions": decision[
                "inclusion_conditions"
            ],
            "evidence": decision["evidence"],
            "source_lineage": source_hashes,
            "downstream_authority": decision[
                "downstream_authority"
            ],
        }
        for decision in included_decisions
    ]

    model_universe = {
        "artifact_id": "PHASE_3_ETF_MODEL_UNIVERSE",
        "model_universe_version": "2026-08-06-v1",
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "model_population_count": len(model_records),
        "reference_population_count": REFERENCE_COUNT,
        "excluded_reference_population_count": len(
            excluded_decisions
        ),
        "selection_rule": {
            "market_screen_state": "MARKET_DATA_ELIGIBLE",
            "five_year_eligibility_required": True,
            "minimum_median_daily_dollar_volume_usd": (
                MINIMUM_MEDIAN_DOLLAR_VOLUME_USD
            ),
            "return_calculation_state": "CALCULATED",
            "allowed_issuer_identity_states": [
                "ISSUER_CONFIRMED",
                "PILOT_COMPLETE",
            ],
        },
        "source_hashes": source_hashes,
        "records": model_records,
    }

    ledger_sha256 = sha256_bytes(
        canonical_json_bytes(decision_ledger)
    )

    model_sha256 = sha256_bytes(
        canonical_json_bytes(model_universe)
    )

    exclusion_reason_counts = Counter(
        reason
        for decision in excluded_decisions
        for reason in decision["exclusion_reasons"]
    )

    certification = {
        "certification_id": (
            "PHASE_3_ETF_MODEL_UNIVERSE_CERTIFICATION"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "certification_state": "CERTIFIED",
        "critical_failures": [],
        "reference_population_count": len(decisions),
        "model_population_count": len(included_decisions),
        "excluded_reference_population_count": len(
            excluded_decisions
        ),
        "required_model_population_count": MODEL_COUNT,
        "required_seeds": sorted(REQUIRED_SEEDS),
        "required_seeds_present": True,
        "decision_ledger_sha256": ledger_sha256,
        "model_universe_sha256": model_sha256,
        "source_hashes": source_hashes,
        "exclusion_reason_counts": dict(
            sorted(exclusion_reason_counts.items())
        ),
        "authority": {
            "taxonomy_development_authorized": True,
            "benchmark_assignment_authorized": False,
            "risk_model_authorized": False,
            "ranking_authorized": False,
            "forecasting_authorized": False,
            "recommendations_authorized": False,
            "allocation_authorized": False,
            "automatic_execution_authorized": False,
            "uip_database_write_authorized": False,
        },
    }

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    with DECISION_LEDGER_PATH.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        json.dump(
            decision_ledger,
            handle,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        handle.write("\n")

    with MODEL_UNIVERSE_PATH.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        json.dump(
            model_universe,
            handle,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        handle.write("\n")

    with CERTIFICATION_PATH_OUT.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        json.dump(
            certification,
            handle,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        handle.write("\n")

    print("=" * 72)
    print("Phase 3 ETF Model-Universe Certification")
    print("=" * 72)
    print(f"Reference population: {len(decisions)}")
    print(f"Model population:     {len(included_decisions)}")
    print(f"Reference-only:       {len(excluded_decisions)}")
    print(f"Required seeds:       {sorted(REQUIRED_SEEDS)}")
    print("Certification state:  CERTIFIED")
    print(f"Model SHA-256:        {model_sha256}")
    print(f"Ledger SHA-256:       {ledger_sha256}")
    print("")
    print(f"Model universe:       {MODEL_UNIVERSE_PATH}")
    print(f"Decision ledger:      {DECISION_LEDGER_PATH}")
    print(f"Certification:        {CERTIFICATION_PATH_OUT}")


if __name__ == "__main__":
    main()
