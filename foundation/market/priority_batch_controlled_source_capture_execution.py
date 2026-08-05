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
    "CAPTURED",
    "CAPTURE_UNRESOLVED",
    "CAPTURE_CONFLICTED",
    "CAPTURE_QUARANTINED",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _host_allowed(url: str, required_domain: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    domain = required_domain.lower()
    return host == domain or host.endswith("." + domain)


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
            redirects = [url] if final_url == url else [url, final_url]
            return {
                "payload": payload,
                "http_status": status,
                "final_url": final_url,
                "redirect_chain": redirects,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        final_url = exc.geturl() or url
        redirects = [url] if final_url == url else [url, final_url]
        return {
            "payload": payload,
            "http_status": int(exc.code),
            "final_url": final_url,
            "redirect_chain": redirects,
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


def _classify(record: dict[str, Any], result: dict[str, Any], required_domain: str) -> tuple[str, list[str]]:
    final_url = str(result.get("final_url") or "")
    status = result.get("http_status")
    payload = result.get("payload") or b""
    text = payload.decode("utf-8", errors="ignore").lower()

    if not final_url.startswith("https://") or not _host_allowed(final_url, required_domain):
        return "CAPTURE_QUARANTINED", ["FINAL_URL_OUTSIDE_OFFICIAL_HTTPS_DOMAIN"]

    if result.get("error") or status is None or int(status) >= 400:
        return "CAPTURE_UNRESOLVED", [str(result.get("error") or f"HTTP_STATUS_{status}")]

    markers = [str(value).lower() for value in record.get("expected_identity_markers", [])]
    if len(markers) != 3:
        return "CAPTURE_CONFLICTED", ["EXPECTED_IDENTITY_MARKER_COUNT_DRIFT"]

    hits = [marker for marker in markers if marker and (marker in text or marker in final_url.lower())]
    series_id = str(record.get("sec_series_id") or "").lower()
    class_id = str(record.get("sec_class_contract_id") or "").lower()

    if series_id in hits and class_id in hits:
        return "CAPTURED", ["SEC_SERIES_AND_CLASS_IDENTITIES_CONFIRMED"]
    if series_id in hits or class_id in hits:
        return "CAPTURE_CONFLICTED", ["ONLY_ONE_SEC_IDENTITY_MARKER_CONFIRMED"]
    return "CAPTURE_UNRESOLVED", ["NO_SEC_SERIES_OR_CLASS_IDENTITY_CONFIRMED"]


def validate_inputs(plan: dict[str, Any], authorization: dict[str, Any], policy: dict[str, Any]) -> None:
    records = list(plan.get("records", []))
    required_count = int(policy["required_record_count"])
    if len(records) != required_count:
        raise ValueError("Capture-plan record count drifted")
    if int(plan.get("plan_record_count", -1)) != required_count:
        raise ValueError("Capture-plan declared count drifted")
    if authorization.get("authorization_complete") is not True:
        raise ValueError("Execution authorization is incomplete")
    if authorization.get("capture_execution_authorized") is not True:
        raise ValueError("Controlled capture execution is not authorized")
    if authorization.get("automatic_execution_authorized") is not False:
        raise ValueError("Automatic execution authority is prohibited")
    if int(authorization.get("authorized_record_count", -1)) != required_count:
        raise ValueError("Authorization record count drifted")
    if authorization.get("authorized_route_type") != policy["required_route_type"]:
        raise ValueError("Authorization route drifted")
    if authorization.get("capture_plan_sha256") != policy["required_capture_plan_sha256"]:
        raise ValueError("Authorization does not lock required plan hash")

    security_ids: list[str] = []
    raw_paths: list[str] = []
    expected_sequence = 1
    for record in records:
        if int(record.get("sequence", -1)) != expected_sequence:
            raise ValueError("Capture-plan sequence is not contiguous")
        expected_sequence += 1
        security_ids.append(str(record.get("security_id") or ""))
        raw_paths.append(str(record.get("raw_path") or ""))
        if record.get("capture_state") not in {"CAPTURE_PENDING", *FINAL_STATES}:
            raise ValueError("Unknown capture state")
        if record.get("route_type") != policy["required_route_type"]:
            raise ValueError("Uncertified route found in capture plan")
        if record.get("official_domain") != policy["required_official_domain"]:
            raise ValueError("Unauthorized official domain")
        request_url = str(record.get("request_url") or "")
        if not request_url.startswith("https://") or not _host_allowed(request_url, policy["required_official_domain"]):
            raise ValueError("Unauthorized request URL")
        for field in ("security_id", "symbol", "sec_cik", "sec_series_id", "sec_class_contract_id", "raw_path"):
            if not record.get(field):
                raise ValueError(f"Missing required capture field: {field}")
        if len(list(record.get("expected_identity_markers", []))) != 3:
            raise ValueError("Expected identity marker count drifted")
        if record.get("capture_authorized") is not False:
            raise ValueError("Premature record-level capture authority")
        if record.get("taxonomy_dimensions_assigned") is not False:
            raise ValueError("Premature taxonomy assignment")

    if len(set(security_ids)) != required_count:
        raise ValueError("Duplicate or missing security identities")
    if len(set(raw_paths)) != required_count:
        raise ValueError("Duplicate immutable raw paths")


def _write_checkpoint(document: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


def execute_capture(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    policy: dict[str, Any],
    output_path: Path,
    user_agent: str,
    fetcher: Callable[[str, str, int], dict[str, Any]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    validate_inputs(plan, authorization, policy)
    if not user_agent or "@" not in user_agent:
        raise ValueError("Declared SEC user agent with contact email is required")

    fetcher = fetcher or _default_fetch
    if output_path.exists():
        result_doc = json.loads(output_path.read_text(encoding="utf-8"))
        validate_inputs(result_doc, authorization, policy)
    else:
        result_doc = deepcopy(plan)
        result_doc["phase"] = "3.6b.3m"
        result_doc["capture_execution_performed"] = True
        result_doc["execution_started_at_utc"] = _utc_now()
        result_doc["authority"] = deepcopy(policy["authority"])
        result_doc["capture_ledger_complete"] = False
        _write_checkpoint(result_doc, output_path)

    timeout = int(policy["execution"]["request_timeout_seconds"])
    retries = int(policy["execution"]["maximum_retry_attempts"])
    interval = 1.0 / max(1, int(policy["execution"]["maximum_requests_per_second"]))
    retryable = {int(value) for value in policy["execution"]["retryable_http_statuses"]}
    backoffs = list(policy["execution"]["retry_backoff_seconds"])

    for record in result_doc["records"]:
        if record.get("capture_state") in FINAL_STATES:
            continue
        if record.get("capture_state") != "CAPTURE_PENDING":
            raise ValueError("Resume ledger contains nonfinal, nonpending state")

        attempt_history: list[dict[str, Any]] = list(record.get("attempt_history") or [])
        final_result: dict[str, Any] | None = None
        for attempt_index in range(retries + 1):
            result = fetcher(record["request_url"], user_agent, timeout)
            payload = result.get("payload") or b""
            if not isinstance(payload, bytes):
                payload = bytes(payload)
            retrieved_at = _utc_now()
            attempt_history.append(
                {
                    "attempt_number": attempt_index + 1,
                    "retrieved_at_utc": retrieved_at,
                    "http_status": result.get("http_status"),
                    "final_url": result.get("final_url"),
                    "redirect_chain": list(result.get("redirect_chain") or [record["request_url"]]),
                    "payload_sha256": _sha256(payload),
                    "failure_reason": result.get("error"),
                }
            )
            final_result = dict(result)
            final_result["payload"] = payload
            status = result.get("http_status")
            should_retry = attempt_index < retries and (status is None or int(status) in retryable)
            if not should_retry:
                break
            sleeper(float(backoffs[min(attempt_index, len(backoffs) - 1)]))

        assert final_result is not None
        payload = final_result["payload"]
        raw_path = Path(record["raw_path"])
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        digest = _sha256(payload)
        if raw_path.exists():
            existing_digest = _sha256(raw_path.read_bytes())
            if existing_digest != digest:
                raise ValueError(f"Immutable raw-path collision for {record['security_id']}")
        else:
            raw_path.write_bytes(payload)

        state, reasons = _classify(record, final_result, policy["required_official_domain"])
        record.update(
            {
                "capture_state": state,
                "attempt_count": len(attempt_history),
                "attempt_history": attempt_history,
                "http_status": final_result.get("http_status"),
                "final_url": final_result.get("final_url"),
                "redirect_chain": list(final_result.get("redirect_chain") or [record["request_url"]]),
                "retrieved_at_utc": attempt_history[-1]["retrieved_at_utc"],
                "payload_sha256": digest,
                "failure_reason": final_result.get("error"),
                "classification_reasons": reasons,
                "capture_authorized": False,
                "taxonomy_dimensions_assigned": False,
                "taxonomy_classification_authorized": False,
                "production_taxonomy_authority": False,
            }
        )
        _write_checkpoint(result_doc, output_path)
        sleeper(interval)

    counts: dict[str, int] = {}
    for record in result_doc["records"]:
        state = str(record.get("capture_state"))
        counts[state] = counts.get(state, 0) + 1
    result_doc["capture_state_counts"] = counts
    result_doc["final_record_count"] = sum(counts.get(state, 0) for state in FINAL_STATES)
    result_doc["capture_ledger_complete"] = result_doc["final_record_count"] == int(policy["required_record_count"])
    result_doc["execution_completed_at_utc"] = _utc_now() if result_doc["capture_ledger_complete"] else None
    result_doc["capture_ledger_certification_authorized"] = False
    result_doc["taxonomy_evidence_normalization_authorized"] = False
    result_doc["production_taxonomy_classification_authorized"] = False
    result_doc["next_required_step"] = "PRIORITY_BATCH_CAPTURE_LEDGER_REVIEW_AND_CERTIFICATION"
    _write_checkpoint(result_doc, output_path)
    return result_doc


def build_summary(result_doc: dict[str, Any], output_path: Path) -> dict[str, Any]:
    payload = output_path.read_bytes()
    return {
        "phase": "3.6b.3m",
        "record_count": len(result_doc.get("records", [])),
        "final_record_count": result_doc.get("final_record_count", 0),
        "capture_state_counts": result_doc.get("capture_state_counts", {}),
        "capture_ledger_complete": result_doc.get("capture_ledger_complete", False),
        "capture_ledger_certification_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": result_doc.get("next_required_step"),
        "capture_ledger_sha256": _sha256(payload),
    }
