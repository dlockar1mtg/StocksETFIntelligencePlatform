from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class RawCaptureError(ValueError):
    """Raised when a raw acquisition capture violates governed controls."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RawCaptureError(f"Unable to load governed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RawCaptureError(f"Governed JSON must be an object: {path}")
    return value


def parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RawCaptureError(f"Invalid timestamp for {field}") from exc
    if parsed.tzinfo is None:
        raise RawCaptureError(f"Timestamp must include timezone: {field}")
    return parsed.astimezone(timezone.utc)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_capture_policy(policy: dict[str, Any]) -> None:
    required_true = (
        "raw_payloads_must_remain_outside_git",
        "raw_records_immutable",
        "content_sha256_required",
    )
    for field in required_true:
        if policy.get(field) is not True:
            raise RawCaptureError(f"Raw capture policy weakened: {field}")
    if policy.get("duplicate_content_policy") != "IDEMPOTENT_REJECT":
        raise RawCaptureError("Duplicate content must be rejected idempotently")
    if policy.get("conflict_policy") != "QUARANTINE":
        raise RawCaptureError("Conflicting captures must be quarantined")
    for field in (
        "certified_market_monitoring_authorized",
        "certified_analytics_authorized",
        "direct_uip_database_writes_authorized",
    ):
        if policy.get(field) is not False:
            raise RawCaptureError(f"Phase 1.2 authority expanded: {field}")


def validate_capture_manifest(
    manifest: dict[str, Any],
    *,
    known_provider_ids: Iterable[str],
    known_domains: Iterable[str],
    known_security_ids: Iterable[str],
    existing_hashes: Iterable[str] = (),
    now_utc: datetime | None = None,
) -> None:
    required = {
        "capture_id",
        "provider_id",
        "data_domain",
        "security_id",
        "source_record_id",
        "observed_at_utc",
        "retrieved_at_utc",
        "captured_at_utc",
        "content_sha256",
        "byte_count",
        "storage_path",
        "capture_state",
    }
    missing = sorted(required - manifest.keys())
    if missing:
        raise RawCaptureError(f"Missing capture fields: {', '.join(missing)}")

    if manifest["provider_id"] not in set(known_provider_ids):
        raise RawCaptureError("Unknown provider is blocked")
    if manifest["data_domain"] not in set(known_domains):
        raise RawCaptureError("Unknown data domain is blocked")
    if manifest["security_id"] not in set(known_security_ids):
        raise RawCaptureError("Unknown security identity is blocked")

    digest = manifest["content_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise RawCaptureError("Invalid SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise RawCaptureError("Invalid SHA-256 digest") from exc
    if digest in set(existing_hashes):
        raise RawCaptureError("Duplicate content hash rejected")

    observed = parse_utc(manifest["observed_at_utc"], "observed_at_utc")
    retrieved = parse_utc(manifest["retrieved_at_utc"], "retrieved_at_utc")
    captured = parse_utc(manifest["captured_at_utc"], "captured_at_utc")
    effective_now = now_utc or datetime.now(timezone.utc)
    if observed > effective_now:
        raise RawCaptureError("Future observation is blocked")
    if retrieved < observed:
        raise RawCaptureError("Retrieval cannot precede observation")
    if captured < retrieved:
        raise RawCaptureError("Capture cannot precede retrieval")

    if not isinstance(manifest["byte_count"], int) or manifest["byte_count"] < 1:
        raise RawCaptureError("Captured payload must have positive byte count")

    state = manifest["capture_state"]
    path = manifest["storage_path"]
    if state == "CAPTURED" and not path.startswith("data/raw/"):
        raise RawCaptureError("Captured content must be stored in raw zone")
    if state == "QUARANTINED" and not path.startswith("data/quarantine/"):
        raise RawCaptureError("Quarantined content must be stored in quarantine zone")
    if state not in {"CAPTURED", "QUARANTINED"}:
        raise RawCaptureError("Only captured or quarantined manifests may be retained")
