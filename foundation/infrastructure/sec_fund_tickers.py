from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "sources" / "sec_fund_ticker_acquisition_policy.json"


class SECFundTickerAcquisitionError(RuntimeError):
    """Raised when governed SEC fund-ticker acquisition cannot complete safely."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("phase") != "2" or policy.get("subphase") != "2A.3":
        raise SECFundTickerAcquisitionError("Unexpected SEC acquisition phase identity")
    if policy.get("selection_principle") != "EVIDENCE_DETERMINES_SIZE":
        raise SECFundTickerAcquisitionError("Evidence-determined sizing is required")
    if policy.get("target_universe_size", "MISSING") is not None:
        raise SECFundTickerAcquisitionError("SEC acquisition may not impose a target universe size")
    if policy.get("raw_evidence_immutable") is not True or policy.get("fail_closed") is not True:
        raise SECFundTickerAcquisitionError("SEC acquisition must be immutable and fail closed")
    if policy.get("maximum_requests_per_second", 99) > policy.get("official_sec_limit_requests_per_second", 10):
        raise SECFundTickerAcquisitionError("Configured request rate exceeds SEC fair-access limit")
    forbidden = (
        "production_data_certification", "analytics", "forecasting", "ranking", "recommendations",
        "portfolio_allocation", "uip_export", "automatic_execution", "direct_uip_database_writes",
    )
    authority = policy.get("authority", {})
    if any(authority.get(name) is not False for name in forbidden):
        raise SECFundTickerAcquisitionError("SEC collector improperly grants downstream authority")
    return policy


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_user_agent(policy: dict[str, Any], explicit: str | None = None) -> str:
    value = explicit or os.getenv(policy["required_user_agent_environment_variable"])
    if not value or "@" not in value or len(value.strip()) < 12:
        raise SECFundTickerAcquisitionError(
            f"Set {policy['required_user_agent_environment_variable']} to an identifying user agent with contact email"
        )
    return value.strip()


def fetch_sec_payload(user_agent: str | None = None, opener=urllib.request.urlopen, sleep=time.sleep) -> tuple[bytes, dict[str, Any]]:
    policy = load_policy()
    agent = _require_user_agent(policy, user_agent)
    request = urllib.request.Request(
        policy["source_url"],
        headers={"User-Agent": agent, "Accept-Encoding": "gzip, deflate", "Accept": "application/json"},
    )
    attempts = int(policy["retry_attempts"])
    backoffs = list(policy["retry_backoff_seconds"])
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with opener(request, timeout=int(policy["timeout_seconds"])) as response:
                payload = response.read()
                if not payload:
                    raise SECFundTickerAcquisitionError("SEC returned an empty payload")
                json.loads(payload.decode("utf-8"))
                retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                return payload, {
                    "source_id": policy["source_id"],
                    "source_url": policy["source_url"],
                    "retrieved_at_utc": retrieved,
                    "authority_level": policy["authority_level"],
                    "source_status": policy["source_status"],
                    "license_class": policy["license_class"],
                    "content_sha256": sha256_bytes(payload),
                    "user_agent_declared": True,
                }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, SECFundTickerAcquisitionError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                sleep(backoffs[min(attempt, len(backoffs) - 1)])
    raise SECFundTickerAcquisitionError(f"SEC acquisition failed after {attempts} attempts: {last_error}")


def parse_fund_ticker_payload(payload: bytes) -> list[dict[str, Any]]:
    document = json.loads(payload.decode("utf-8"))
    rows = document.get("data")
    fields = document.get("fields")
    if not isinstance(rows, list) or not isinstance(fields, list):
        raise SECFundTickerAcquisitionError("Unexpected SEC mutual-fund ticker payload shape")
    normalized_fields = [str(field).strip().lower() for field in fields]
    required = {"cik", "seriesid", "classid", "ticker"}
    if not required.issubset(set(normalized_fields)):
        raise SECFundTickerAcquisitionError(f"SEC payload missing required fields: {sorted(required - set(normalized_fields))}")
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(normalized_fields):
            raise SECFundTickerAcquisitionError("Malformed SEC ticker row")
        item = dict(zip(normalized_fields, row))
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        output.append({
            "ticker": ticker,
            "cik": str(item.get("cik") or "").zfill(10),
            "series_id": item.get("seriesid"),
            "class_contract_id": item.get("classid"),
            "fund_name": item.get("name") or item.get("seriesname") or item.get("classname"),
        })
    return output


def reconcile_to_universe(sec_rows: list[dict[str, Any]], universe_records: list[dict[str, Any]]) -> dict[str, Any]:
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in sec_rows:
        by_ticker.setdefault(row["ticker"], []).append(row)
    reconciled: list[dict[str, Any]] = []
    matched = conflicted = unmatched = 0
    for source in universe_records:
        ticker = str(source.get("symbol") or source.get("ticker") or "").strip().upper()
        security_id = source.get("security_id")
        candidates = by_ticker.get(ticker, [])
        unique = {(item["cik"], item["series_id"], item["class_contract_id"]) for item in candidates}
        if len(unique) == 1:
            candidate = candidates[0]
            state = "MATCHED"
            matched += 1
        elif len(unique) > 1:
            candidate = None
            state = "CONFLICTED"
            conflicted += 1
        else:
            candidate = None
            state = "UNMATCHED"
            unmatched += 1
        reconciled.append({
            "security_id": security_id,
            "symbol": ticker,
            "reconciliation_state": state,
            "sec_cik": candidate["cik"] if candidate else None,
            "sec_series_id": candidate["series_id"] if candidate else None,
            "sec_class_contract_id": candidate["class_contract_id"] if candidate else None,
            "sec_fund_name": candidate["fund_name"] if candidate else None,
            "candidate_count": len(candidates),
            "analytics_authorized": False,
            "recommendations_authorized": False,
        })
    return {
        "total_universe_records": len(universe_records),
        "matched": matched,
        "conflicted": conflicted,
        "unmatched": unmatched,
        "records": reconciled,
        "selection_principle": "EVIDENCE_DETERMINES_SIZE",
        "target_universe_size": None,
    }


def write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise SECFundTickerAcquisitionError(f"Immutable raw-evidence collision: {path}")
        return
    path.write_bytes(payload)
