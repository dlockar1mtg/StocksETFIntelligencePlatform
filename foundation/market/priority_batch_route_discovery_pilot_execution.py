from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


FINAL_STATES = {
    "PRODUCT_SPECIFIC_RESOLVED",
    "GENERIC_LANDING_PAGE",
    "DISCOVERY_UNRESOLVED",
    "DISCOVERY_CONFLICTED",
    "DISCOVERY_QUARANTINED",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _host_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in allowed_domains)


def _build_url(record: dict[str, Any], request: dict[str, Any], policy: dict[str, Any]) -> str:
    templates = policy["execution"]
    route_type = request["route_type"]
    if route_type == "SEC_SERIES_CLASS_FILING_DISCOVERY":
        return templates["sec_search_template"].format(
            cik=record["sec_cik"],
            series_id=record["sec_series_id"],
            class_contract_id=record["sec_class_contract_id"],
        )
    if route_type == "ISHARES_SYMBOL_PRODUCT_DISCOVERY":
        return templates["ishares_search_template"].format(
            symbol=urllib.parse.quote(str(record["symbol"]), safe="")
        )
    raise ValueError(f"Unsupported route type: {route_type}")


def _default_fetch(url: str, user_agent: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            final_url = response.geturl()
            status = int(getattr(response, "status", 200))
            redirect_chain = [url] if final_url == url else [url, final_url]
            return {
                "payload": payload,
                "http_status": status,
                "final_url": final_url,
                "redirect_chain": redirect_chain,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return {
            "payload": payload,
            "http_status": int(exc.code),
            "final_url": exc.geturl() or url,
            "redirect_chain": [url, exc.geturl()] if exc.geturl() and exc.geturl() != url else [url],
            "error": f"HTTP_ERROR_{exc.code}",
        }
    except Exception as exc:  # noqa: BLE001 - preserved as governed evidence
        return {
            "payload": str(exc).encode("utf-8", errors="replace"),
            "http_status": None,
            "final_url": url,
            "redirect_chain": [url],
            "error": f"REQUEST_ERROR:{type(exc).__name__}:{exc}",
        }


def _classify(
    record: dict[str, Any],
    request: dict[str, Any],
    result: dict[str, Any],
    allowed_domains: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    final_url = str(result.get("final_url") or "")
    status = result.get("http_status")
    payload = result.get("payload") or b""
    text = payload.decode("utf-8", errors="ignore").lower()

    if not final_url.startswith("https://") or not _host_allowed(final_url, allowed_domains):
        return "DISCOVERY_QUARANTINED", ["FINAL_URL_OUTSIDE_OFFICIAL_HTTPS_DOMAIN"]
    if result.get("error") or status is None or int(status) >= 400:
        return "DISCOVERY_UNRESOLVED", [str(result.get("error") or f"HTTP_STATUS_{status}")]

    symbol = str(record["symbol"]).lower()
    series_id = str(record["sec_series_id"]).lower()
    class_id = str(record["sec_class_contract_id"]).lower()
    route_type = request["route_type"]

    if route_type == "SEC_SERIES_CLASS_FILING_DISCOVERY":
        marker_hits = [marker for marker in (series_id, class_id, symbol) if marker in text or marker in final_url.lower()]
        if series_id in marker_hits or class_id in marker_hits:
            return "PRODUCT_SPECIFIC_RESOLVED", ["SEC_SERIES_OR_CLASS_IDENTITY_CONFIRMED"]
        if symbol in marker_hits:
            return "GENERIC_LANDING_PAGE", ["SYMBOL_ONLY_WITHOUT_SEC_SERIES_CLASS_CONFIRMATION"]
        return "GENERIC_LANDING_PAGE", ["NO_SECURITY_LEVEL_IDENTITY_MARKER"]

    if route_type == "ISHARES_SYMBOL_PRODUCT_DISCOVERY":
        url_text = final_url.lower()
        symbol_hit = symbol in text or symbol in url_text
        product_path = "/products/" in url_text or "/product" in url_text
        if symbol_hit and product_path:
            return "PRODUCT_SPECIFIC_RESOLVED", ["ISHARES_SYMBOL_AND_PRODUCT_PATH_CONFIRMED"]
        if symbol_hit:
            return "GENERIC_LANDING_PAGE", ["SYMBOL_PRESENT_WITHOUT_PRODUCT_SPECIFIC_PATH"]
        return "GENERIC_LANDING_PAGE", ["GENERIC_ISHARES_SEARCH_OR_LANDING_PAGE"]

    return "DISCOVERY_CONFLICTED", ["UNSUPPORTED_ROUTE_TYPE"]


def validate_inputs(pilot: dict[str, Any], policy: dict[str, Any]) -> None:
    records = list(pilot.get("records", []))
    if len(records) != int(policy["required_pilot_record_count"]):
        raise ValueError("Pilot record count drifted")
    security_ids = [record.get("security_id") for record in records]
    if len(set(security_ids)) != len(security_ids):
        raise ValueError("Duplicate pilot security identity")
    request_count = 0
    for record in records:
        if record.get("pilot_state") != policy["required_input_state"]:
            raise ValueError("Pilot record is not pending")
        for field in ("security_id", "symbol", "sec_cik", "sec_series_id", "sec_class_contract_id"):
            if not record.get(field):
                raise ValueError(f"Missing required pilot field: {field}")
        requests = list(record.get("discovery_requests", []))
        if len(requests) != 2:
            raise ValueError("Each pilot record must contain exactly two requests")
        for request in requests:
            request_count += 1
            if request.get("route_type") not in policy["allowed_route_types"]:
                raise ValueError("Unauthorized route type")
            if request.get("discovery_state") != policy["required_input_state"]:
                raise ValueError("Discovery request is not pending")
            if request.get("capture_authorized") is not False:
                raise ValueError("Premature capture authority")
    if request_count != int(policy["required_request_count"]):
        raise ValueError("Pilot request count drifted")


def execute_pilot(
    pilot: dict[str, Any],
    policy: dict[str, Any],
    output_path: Path,
    raw_directory: Path,
    user_agent: str,
    fetcher: Callable[[str, str, int], dict[str, Any]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    validate_inputs(pilot, policy)
    if not user_agent or "@" not in user_agent:
        raise ValueError("Declared user agent with contact email is required")

    fetcher = fetcher or _default_fetch
    raw_directory.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_doc = deepcopy(pilot)
    result_doc["phase"] = "3.6b.3i"
    result_doc["discovery_execution_performed"] = True
    result_doc["execution_started_at_utc"] = _utc_now()
    result_doc["authority"] = deepcopy(policy["authority"])

    interval = 1.0 / max(1, int(policy["execution"]["maximum_requests_per_second"]))
    timeout = int(policy["execution"]["request_timeout_seconds"])
    state_counts: dict[str, int] = {}
    request_state_counts: dict[str, int] = {}

    for record in result_doc["records"]:
        record_states: list[str] = []
        for request in record["discovery_requests"]:
            url = _build_url(record, request, policy)
            if not url.startswith("https://") or not _host_allowed(url, policy["official_domains"]):
                raise ValueError("Constructed discovery URL violates domain policy")

            result = fetcher(url, user_agent, timeout)
            payload = result.get("payload") or b""
            if not isinstance(payload, bytes):
                payload = bytes(payload)
            retrieved_at = _utc_now()
            digest = _sha256(payload)
            route_slug = request["route_type"].lower()
            raw_path = raw_directory / f"{record['security_id']}_{route_slug}.bin"
            raw_path.write_bytes(payload)

            state, reasons = _classify(record, request, result, policy["official_domains"])
            request.update(
                {
                    "discovery_state": state,
                    "resolved_url": url,
                    "final_url": result.get("final_url"),
                    "redirect_chain": list(result.get("redirect_chain") or [url]),
                    "http_status": result.get("http_status"),
                    "retrieved_at_utc": retrieved_at,
                    "payload_sha256": digest,
                    "raw_path": str(raw_path),
                    "failure_reason": result.get("error"),
                    "classification_reasons": reasons,
                    "capture_authorized": False,
                }
            )
            record_states.append(state)
            request_state_counts[state] = request_state_counts.get(state, 0) + 1
            output_path.write_text(json.dumps(result_doc, indent=2, sort_keys=True), encoding="utf-8")
            sleeper(interval)

        if all(state == "PRODUCT_SPECIFIC_RESOLVED" for state in record_states):
            record_state = "DISCOVERY_RESOLVED"
        elif any(state in {"DISCOVERY_CONFLICTED", "DISCOVERY_QUARANTINED"} for state in record_states):
            record_state = "DISCOVERY_CONFLICTED"
        elif any(state == "PRODUCT_SPECIFIC_RESOLVED" for state in record_states):
            record_state = "DISCOVERY_RESOLVED"
        else:
            record_state = "DISCOVERY_UNRESOLVED"
        record["pilot_state"] = record_state
        record["source_capture_authorized"] = False
        record["taxonomy_dimensions_assigned"] = False
        record["taxonomy_classification_authorized"] = False
        record["production_taxonomy_authority"] = False
        state_counts[record_state] = state_counts.get(record_state, 0) + 1

    result_doc["pilot_state_counts"] = state_counts
    result_doc["request_result_state_counts"] = request_state_counts
    result_doc["execution_completed_at_utc"] = _utc_now()
    result_doc["full_batch_capture_authorized"] = False
    result_doc["next_required_step"] = "PILOT_ROUTE_RELIABILITY_REVIEW_AND_CERTIFICATION"
    output_path.write_text(json.dumps(result_doc, indent=2, sort_keys=True), encoding="utf-8")
    return result_doc


def build_summary(result_doc: dict[str, Any], output_path: Path) -> dict[str, Any]:
    payload = output_path.read_bytes()
    return {
        "phase": "3.6b.3i",
        "pilot_record_count": len(result_doc.get("records", [])),
        "request_count": sum(len(record.get("discovery_requests", [])) for record in result_doc.get("records", [])),
        "pilot_state_counts": result_doc.get("pilot_state_counts", {}),
        "request_result_state_counts": result_doc.get("request_result_state_counts", {}),
        "full_batch_capture_authorized": False,
        "next_required_step": result_doc.get("next_required_step"),
        "execution_ledger_sha256": _sha256(payload),
    }
