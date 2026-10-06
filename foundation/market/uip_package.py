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
PACKAGE_FORMAT = "etf-provisional-universe-v1"


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
    writer.writerow(["security_id", "symbol", "as_of_date", "close", "quality_status", "freshness_state", "source_tier"])
    for r in records:
        writer.writerow([r["security_id"], r["symbol"], r.get("as_of_date") or "", r.get("close") or "",
                         r["quality_status"], r["freshness_state"], r.get("source_tier") or ""])
    return buffer.getvalue()


def package_validation(records: list[dict], seeds: list[str]) -> tuple[str, list[str]]:
    """FAIL when no seed fund is usable; PASS_WITH_LIMITATIONS when some funds are not current."""
    usable = {r["symbol"] for r in records if r["quality_status"] in ("PASS", "PROVISIONAL")}
    if not usable & set(seeds):
        return "FAIL", ["No seed fund has usable market data."]
    blocked = sorted(r["symbol"] for r in records if r["quality_status"] not in ("PASS", "PROVISIONAL"))
    stale = sorted(r["symbol"] for r in records if r["quality_status"] in ("PASS", "PROVISIONAL") and r["freshness_state"] != "CURRENT")
    limits = []
    if blocked:
        limits.append(f"{len(blocked)} funds without usable data this run")
    if stale:
        limits.append(f"{len(stale)} funds not current")
    return ("PASS_WITH_LIMITATIONS" if limits else "PASS"), limits


def write_package(out_dir: Path, *, files: dict[str, tuple[bytes, int]], validation: str, commit: str,
                  generated_at_utc: str, as_of: str, schema: dict, snapshot: bytes) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    listed = []
    for name, (data, rows) in files.items():
        (out_dir / name).write_bytes(data)
        listed.append({"path": name, "sha256": sha256_bytes(data), "row_count": rows})
    manifest = {
        "package_id": f"etf-{as_of}-{sha256_bytes(b''.join(d for d, _ in files.values()))[:12]}",
        "domain": "stocks_etf", "contract_version": CONTRACT_VERSION, "generated_at_utc": generated_at_utc,
        "source_snapshot_id": f"market-data-status-{sha256_bytes(snapshot)[:16]}", "repository_commit": commit,
        "files": listed, "validation_status": validation, "certification_status": "PROVISIONAL",
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
