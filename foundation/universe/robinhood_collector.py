from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


class RobinhoodCollectorError(ValueError):
    """Raised when Robinhood availability collection violates governed controls."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _boolean_capability(instrument: dict[str, Any], field: str) -> bool | None:
    if field not in instrument:
        return None
    value = instrument.get(field)
    return value if isinstance(value, bool) else None


def _fractional_capability(instrument: dict[str, Any]) -> bool | None:
    if "fractional_tradability" not in instrument:
        return None
    value = str(instrument.get("fractional_tradability", "")).lower()
    if value in {"tradable", "tradeable"}:
        return True
    if value in {"unavailable", "not_tradable", "not_tradeable", "position_closing_only"}:
        return False
    return None


def classify_instrument(candidate: dict[str, Any], payload: dict[str, Any], *, retrieved_at_utc: str, source_url: str, raw_sha256: str) -> dict[str, Any]:
    results = payload.get("results")
    if not isinstance(results, list):
        status = "UNKNOWN"
        instrument: dict[str, Any] = {}
    else:
        exact = [item for item in results if str(item.get("symbol", "")).upper() == str(candidate["symbol"]).upper()]
        if len(exact) > 1:
            status = "CONFLICTED"
            instrument = {}
        elif not exact:
            status = "NOT_FOUND"
            instrument = {}
        else:
            instrument = exact[0]
            tradability = str(instrument.get("tradability", "")).lower()
            state = str(instrument.get("state", "")).lower()
            tradeable = instrument.get("tradeable") is True
            if state in {"inactive", "delisted"}:
                status = "DELISTED"
            elif tradability in {"position_closing_only", "sell_only"}:
                status = "SELL_ONLY"
            elif tradeable and tradability in {"tradable", "tradeable"}:
                status = "ELIGIBLE"
            elif state in {"temporarily_unavailable", "halted"}:
                status = "TEMPORARILY_UNAVAILABLE"
            elif instrument:
                status = "PURCHASE_RESTRICTED"
            else:
                status = "UNKNOWN"

    fractional = _fractional_capability(instrument)
    recurring = _boolean_capability(instrument, "recurring_investment_eligible")
    drip = _boolean_capability(instrument, "drip_eligible")

    return {
        "security_id": candidate["security_candidate_id"],
        "symbol": candidate["symbol"],
        "broker_id": "ROBINHOOD-US",
        "broker_status": status,
        "whole_share_supported": status == "ELIGIBLE",
        "fractional_share_supported": fractional,
        "recurring_investment_supported": recurring,
        "dividend_reinvestment_supported": drip,
        "fractional_share_evidence_state": "KNOWN" if fractional is not None else "UNKNOWN",
        "recurring_investment_evidence_state": "KNOWN" if recurring is not None else "UNKNOWN",
        "dividend_reinvestment_evidence_state": "KNOWN" if drip is not None else "UNKNOWN",
        "robinhood_instrument_id": instrument.get("id"),
        "verified_at_utc": retrieved_at_utc,
        "effective_at_utc": retrieved_at_utc,
        "available_at_utc": retrieved_at_utc,
        "verification_method": "BROKER_SEARCH_RESULT",
        "verification_confidence": 1.0 if status not in {"UNKNOWN", "CONFLICTED"} else 0.0,
        "source_id": "ROBINHOOD-PUBLIC-INSTRUMENT-LOOKUP",
        "source_record_id": instrument.get("id") or candidate["symbol"],
        "source_url": source_url,
        "content_sha256": raw_sha256,
        "broker_eligible": status == "ELIGIBLE",
        "analytics_eligible": False,
        "collection_error": None,
    }


def fetch_symbol(symbol: str, *, url_template: str, timeout_seconds: int = 30) -> tuple[dict[str, Any], bytes, str]:
    url = url_template.format(symbol=urllib.parse.quote(symbol))
    request = urllib.request.Request(url, headers={"User-Agent": "StocksETFIntelligencePlatform/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except Exception as exc:
        raise RobinhoodCollectorError(f"Robinhood lookup failed for {symbol}") from exc
    if not raw:
        raise RobinhoodCollectorError(f"Robinhood lookup returned no content for {symbol}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RobinhoodCollectorError(f"Robinhood lookup returned invalid JSON for {symbol}") from exc
    if not isinstance(payload, dict):
        raise RobinhoodCollectorError(f"Robinhood lookup returned non-object JSON for {symbol}")
    return payload, raw, url


def collect_availability(
    candidates: Iterable[dict[str, Any]],
    *,
    output_root: Path,
    operating_date: str,
    url_template: str,
    minimum_delay_seconds: float = 0.25,
    checkpoint_every_records: int = 100,
    fetcher: Callable[..., tuple[dict[str, Any], bytes, str]] = fetch_symbol,
    max_records: int | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    staged_root = output_root / "staged" / operating_date
    raw_root = output_root / "raw" / operating_date / "robinhood"
    quarantine_root = output_root / "quarantine" / operating_date
    staged_root.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)
    quarantine_root.mkdir(parents=True, exist_ok=True)

    result_path = staged_root / "robinhood_availability_records.jsonl"
    checkpoint_path = staged_root / "robinhood_availability_checkpoint.json"
    manifest_path = staged_root / "robinhood_availability_manifest.json"

    completed: dict[str, dict[str, Any]] = {}
    if result_path.exists():
        for line in result_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                record.setdefault("collection_error", None)
                if retry_failed and record.get("collection_error"):
                    continue
                completed[record["symbol"]] = record

    candidate_list = list(candidates)
    if max_records is not None:
        candidate_list = candidate_list[:max_records]

    processed_since_start = 0
    with result_path.open("a", encoding="utf-8") as handle:
        for candidate in candidate_list:
            symbol = candidate["symbol"]
            if symbol in completed:
                continue
            try:
                payload, raw, url = fetcher(symbol, url_template=url_template)
                retrieved = _utc_now()
                digest = sha256_bytes(raw)
                raw_path = raw_root / f"{symbol}.json"
                raw_path.write_bytes(raw)
                record = classify_instrument(candidate, payload, retrieved_at_utc=retrieved, source_url=url, raw_sha256=digest)
            except Exception as exc:
                record = {
                    "security_id": candidate["security_candidate_id"],
                    "symbol": symbol,
                    "broker_id": "ROBINHOOD-US",
                    "broker_status": "UNKNOWN",
                    "whole_share_supported": False,
                    "fractional_share_supported": None,
                    "recurring_investment_supported": None,
                    "dividend_reinvestment_supported": None,
                    "fractional_share_evidence_state": "UNKNOWN",
                    "recurring_investment_evidence_state": "UNKNOWN",
                    "dividend_reinvestment_evidence_state": "UNKNOWN",
                    "robinhood_instrument_id": None,
                    "verified_at_utc": _utc_now(),
                    "verification_method": "BROKER_SEARCH_RESULT",
                    "verification_confidence": 0.0,
                    "source_id": "ROBINHOOD-PUBLIC-INSTRUMENT-LOOKUP",
                    "source_record_id": symbol,
                    "source_url": None,
                    "content_sha256": "0" * 64,
                    "broker_eligible": False,
                    "analytics_eligible": False,
                    "collection_error": str(exc),
                }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            completed[symbol] = record
            processed_since_start += 1
            if processed_since_start % checkpoint_every_records == 0:
                checkpoint_path.write_text(json.dumps({"operating_date": operating_date, "completed_count": len(completed), "last_symbol": symbol, "updated_at_utc": _utc_now()}, indent=2) + "\n", encoding="utf-8")
            if minimum_delay_seconds > 0:
                time.sleep(minimum_delay_seconds)

    records = [completed[candidate["symbol"]] for candidate in candidate_list if candidate["symbol"] in completed]
    result_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")

    counts: dict[str, int] = {}
    for record in records:
        counts[record["broker_status"]] = counts.get(record["broker_status"], 0) + 1
    failures = [record for record in records if record.get("collection_error")]
    failure_path = quarantine_root / "robinhood_availability_failures.json"
    failure_path.write_text(json.dumps(failures, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "collector_id": "ROBINHOOD-US-ETF-AVAILABILITY",
        "operating_date": operating_date,
        "generated_at_utc": _utc_now(),
        "input_candidate_count": len(candidate_list),
        "completed_count": len(records),
        "status_counts": counts,
        "broker_eligible_count": counts.get("ELIGIBLE", 0),
        "failed_lookup_count": len(failures),
        "resume_supported": True,
        "retry_failed_supported": True,
        "missing_capability_evidence_preserved_as_unknown": True,
        "availability_file": str(result_path),
        "availability_file_sha256": sha256_bytes(result_path.read_bytes()),
        "failure_file": str(failure_path),
        "failure_file_sha256": sha256_bytes(failure_path.read_bytes()),
        "analytics_eligibility_implied": False,
        "automatic_execution_authorized": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
