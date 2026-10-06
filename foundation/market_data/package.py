"""The daily governed UIP package: versioned, checksummed files under a manifest that follows
contracts/uip/package_manifest.schema.json. The UIP imports packages; it never reads this repo's data."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "1.0.0"
PACKAGE_FORMAT = "etf-v1-package"


class PackageError(ValueError):
    """Raised when a package or manifest violates the UIP contract."""


def _check(schema: dict, value: Any, where: str) -> None:
    """Validate the JSON-schema subset the manifest contract uses."""
    if "const" in schema and value != schema["const"]:
        raise PackageError(f"{where}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise PackageError(f"{where}: {value!r} not allowed")
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            raise PackageError(f"{where}: must be an object")
        missing = [k for k in schema.get("required", []) if k not in value]
        if missing:
            raise PackageError(f"{where}: missing {missing}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                raise PackageError(f"{where}: unexpected {extra}")
        for key, sub in props.items():
            if key in value:
                _check(sub, value[key], f"{where}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or len(value) < schema.get("minItems", 0):
            raise PackageError(f"{where}: must be an array of at least {schema.get('minItems', 0)}")
        for i, item in enumerate(value):
            _check(schema.get("items", {}), item, f"{where}[{i}]")
    elif kind == "string":
        if not isinstance(value, str) or len(value) < schema.get("minLength", 0):
            raise PackageError(f"{where}: must be a string")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise PackageError(f"{where}: does not match {schema['pattern']}")
    elif kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or value < schema.get("minimum", value):
            raise PackageError(f"{where}: must be an integer >= {schema.get('minimum')}")


def validate_manifest(schema: dict, manifest: dict) -> None:
    _check(schema, manifest, "manifest")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def latest_prices_csv(records: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["security_id", "ticker", "as_of_date", "close", "quality_status", "freshness_state", "source_tier"])
    for r in records:
        writer.writerow([r["security_id"], r["ticker"], r.get("as_of_date") or "", r.get("close") or "",
                         r["quality_status"], r["freshness_state"], r.get("source_tier") or ""])
    return buffer.getvalue()


def package_validation(records: list[dict]) -> tuple[str, list[str]]:
    """PASS needs every held fund usable and current; FAIL only when none is usable."""
    limits: list[str] = []
    usable = [r for r in records if r["quality_status"] in ("PASS", "PROVISIONAL")]
    if not usable:
        return "FAIL", ["No held fund has usable market data."]
    for r in records:
        if r["quality_status"] not in ("PASS", "PROVISIONAL"):
            limits.append(f"{r['ticker']}: {r['quality_status'].lower()}, last good close kept")
        elif r["freshness_state"] != "CURRENT":
            limits.append(f"{r['ticker']}: {r['freshness_state'].lower()} (as of {r.get('as_of_date')})")
        for note in r.get("limitations", []):
            if "single-source" in note:
                limits.append(f"{r['ticker']}: single-source closes this run")
    return ("PASS_WITH_LIMITATIONS" if limits else "PASS"), limits


def write_package(out_dir: Path, *, records: list[dict], research: dict, status: dict, commit: str,
                  generated_at_utc: str, schema: dict) -> dict:
    as_of = max((r.get("as_of_date") or "" for r in records), default="") or generated_at_utc[:10]
    validation, limitations = package_validation(records)
    funds_doc = {"package_format": PACKAGE_FORMAT, "model_version": "etf-v1", "as_of_date": as_of,
                 "generated_at_utc": generated_at_utc, "funds": records, "limitations": limitations,
                 "automatic_execution_authorized": False}
    research_doc = {k: research[k] for k in ("model_id", "generated_at_utc", "history_from", "timing_rules",
                                             "cross_sectional_momentum", "gate", "any_rule_passes") if k in research}
    research_doc["signal_study_pooled"] = (research.get("signal_study") or {}).get("pooled")
    payloads = {
        "funds.json": (json.dumps(funds_doc, indent=1) + "\n").encode("utf-8"),
        "latest_prices.csv": latest_prices_csv(records).encode("utf-8"),
        "research.json": (json.dumps(research_doc, indent=1) + "\n").encode("utf-8"),
        "market_data_status.json": (json.dumps(status, indent=1) + "\n").encode("utf-8"),
    }
    rows = {"funds.json": len(records), "latest_prices.csv": len(records),
            "research.json": len(research_doc.get("timing_rules") or {}), "market_data_status.json": len(status.get("funds", []))}
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name, data in payloads.items():
        (out_dir / name).write_bytes(data)
        files.append({"path": name, "sha256": sha256_bytes(data), "row_count": rows[name]})
    snapshot = sha256_bytes(payloads["market_data_status.json"])
    manifest = {
        "package_id": f"etf-{as_of}-{sha256_bytes(payloads['funds.json'])[:12]}",
        "domain": "stocks_etf", "contract_version": CONTRACT_VERSION, "generated_at_utc": generated_at_utc,
        "source_snapshot_id": f"market-data-status-{snapshot[:16]}", "repository_commit": commit,
        "files": files, "validation_status": validation, "certification_status": "PROVISIONAL",
        "automatic_execution_authorized": False,
    }
    validate_manifest(schema, manifest)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_package(directory: Path, schema: dict) -> dict:
    """What an importer checks: a valid manifest and every file present with its recorded digest."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    validate_manifest(schema, manifest)
    for item in manifest["files"]:
        path = directory / item["path"]
        if not path.is_file() or sha256_bytes(path.read_bytes()) != item["sha256"]:
            raise PackageError(f"{item['path']}: missing or digest mismatch")
    if manifest["validation_status"] == "FAIL":
        raise PackageError("package validation failed")
    return manifest
