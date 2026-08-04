from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SECRegistrantEnrichmentError(ValueError):
    pass


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        return document["records"]
    raise SECRegistrantEnrichmentError("RECORD_ARRAY_MISSING")


def _cik10(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    return text.zfill(10)


def extract_required_ciks(identity_document: Any, pilot_ids: set[str]) -> list[str]:
    ciks: set[str] = set()
    for record in _records(identity_document):
        if record.get("security_id") in pilot_ids:
            continue
        if record.get("resolution_state") not in {"SEC_IDENTITY_CONFIRMED", "MATCHED"}:
            continue
        cik = _cik10(record.get("sec_cik"))
        if cik:
            ciks.add(cik)
    return sorted(ciks)


def normalize_sec_submission(payload: bytes, requested_cik: str, retrieved_at_utc: str) -> dict[str, Any]:
    digest = hashlib.sha256(payload).hexdigest()
    try:
        document = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        return {"cik": requested_cik, "state": "REGISTRANT_QUARANTINED", "reasons": ["INVALID_SEC_JSON"], "payload_sha256": digest, "retrieved_at_utc": retrieved_at_utc, "registrant_name": None}
    returned = _cik10(document.get("cik"))
    name = str(document.get("name") or "").strip()
    if returned != requested_cik:
        return {"cik": requested_cik, "state": "REGISTRANT_CONFLICTED", "reasons": ["RETURNED_CIK_MISMATCH"], "payload_sha256": digest, "retrieved_at_utc": retrieved_at_utc, "registrant_name": None}
    if not name:
        return {"cik": requested_cik, "state": "REGISTRANT_QUARANTINED", "reasons": ["SEC_REGISTRANT_NAME_MISSING"], "payload_sha256": digest, "retrieved_at_utc": retrieved_at_utc, "registrant_name": None}
    return {"cik": requested_cik, "state": "REGISTRANT_CONFIRMED", "reasons": [], "payload_sha256": digest, "retrieved_at_utc": retrieved_at_utc, "registrant_name": name}


def collect_registry(ciks: list[str], raw_directory: Path, user_agent: str, delay_seconds: float = 0.12) -> dict[str, Any]:
    if not user_agent or "@" not in user_agent:
        raise SECRegistrantEnrichmentError("DECLARED_SEC_USER_AGENT_REQUIRED")
    raw_directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for cik in ciks:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        retrieved = datetime.now(timezone.utc).isoformat()
        request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
            raw_path = raw_directory / f"CIK{cik}.json"
            if raw_path.exists() and raw_path.read_bytes() != payload:
                raw_path = raw_directory / f"CIK{cik}_{hashlib.sha256(payload).hexdigest()[:12]}.json"
            raw_path.write_bytes(payload)
            record = normalize_sec_submission(payload, cik, retrieved)
            record.update({"source_tier": "SEC_SUBMISSIONS_API", "source_url": url, "raw_path": str(raw_path)})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            record = {"cik": cik, "state": "REGISTRANT_UNRESOLVED", "reasons": ["SEC_SUBMISSION_CAPTURE_FAILED"], "registrant_name": None, "payload_sha256": None, "retrieved_at_utc": retrieved, "source_tier": "SEC_SUBMISSIONS_API", "source_url": url, "raw_path": None, "error_type": type(exc).__name__}
        records.append(record)
        time.sleep(delay_seconds)
    counts = Counter(record["state"] for record in records)
    return {"phase": "3.6b.3d.1", "unique_cik_count": len(ciks), "record_count": len(records), "state_counts": dict(sorted(counts.items())), "coverage_complete": counts.get("REGISTRANT_CONFIRMED", 0) == len(ciks), "next_required_step": "PHASE_3_6B_3D_ISSUER_IDENTITY_LEDGER_REBUILD" if counts.get("REGISTRANT_CONFIRMED", 0) == len(ciks) else "SEC_REGISTRANT_REMEDIATION", "records": records}


def write_outputs(result: dict[str, Any], output: Path, summary: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {key: value for key, value in result.items() if key != "records"}
    payload["registry_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
