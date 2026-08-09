from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


class HistoricalShardCaptureError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(value, dict):
        raise HistoricalShardCaptureError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def validate_manifest(
    manifest: dict[str, Any],
    expected_manifest_sha256: str,
    manifest_bytes: bytes,
) -> list[dict[str, Any]]:
    if sha256_bytes(manifest_bytes) != expected_manifest_sha256:
        raise HistoricalShardCaptureError(
            "MANIFEST_SHA256_MISMATCH"
        )

    if manifest.get("phase") != "3.6b.3r":
        raise HistoricalShardCaptureError(
            "PHASE_MISMATCH"
        )

    if manifest.get("target_symbols") != [
        "AAXJ",
        "ACWI",
        "IBTJ",
        "IWN",
    ]:
        raise HistoricalShardCaptureError(
            "TARGET_SCOPE_MISMATCH"
        )

    if int(manifest.get("target_record_count", -1)) != 4:
        raise HistoricalShardCaptureError(
            "TARGET_COUNT_MISMATCH"
        )

    if int(manifest.get("historical_shard_count", -1)) != 12:
        raise HistoricalShardCaptureError(
            "SHARD_COUNT_MISMATCH"
        )

    execution = manifest["execution_contract"]

    if int(execution["maximum_unique_sec_requests"]) != 12:
        raise HistoricalShardCaptureError(
            "REQUEST_CEILING_MISMATCH"
        )

    if int(execution["maximum_requests_per_second"]) != 1:
        raise HistoricalShardCaptureError(
            "REQUEST_RATE_MISMATCH"
        )

    if int(execution["maximum_retry_attempts"]) != 0:
        raise HistoricalShardCaptureError(
            "RETRIES_MUST_BE_ZERO"
        )

    if execution["cache_identical_requests"] is not True:
        raise HistoricalShardCaptureError(
            "REQUEST_CACHE_REQUIRED"
        )

    if execution["immutable_raw_storage"] is not True:
        raise HistoricalShardCaptureError(
            "IMMUTABLE_STORAGE_REQUIRED"
        )

    authority = manifest["authority"]

    if authority["historical_shard_network_capture_authorized"] is not False:
        raise HistoricalShardCaptureError(
            "MANIFEST_MUST_NOT_SELF_AUTHORIZE_NETWORK"
        )

    if authority["filing_header_capture_authorized"] is not False:
        raise HistoricalShardCaptureError(
            "FILING_HEADER_CAPTURE_MUST_REMAIN_FALSE"
        )

    if authority["filing_document_capture_authorized"] is not False:
        raise HistoricalShardCaptureError(
            "FILING_DOCUMENT_CAPTURE_MUST_REMAIN_FALSE"
        )

    if authority["full_priority_population_execution_authorized"] is not False:
        raise HistoricalShardCaptureError(
            "FULL_PRIORITY_EXECUTION_MUST_REMAIN_FALSE"
        )

    if authority["taxonomy_evidence_normalization_authorized"] is not False:
        raise HistoricalShardCaptureError(
            "TAXONOMY_NORMALIZATION_MUST_REMAIN_FALSE"
        )

    shards = list(
        manifest.get(
            "historical_shards",
            [],
        )
    )

    expected_names = [
        f"CIK0001100663-submissions-{index:03d}.json"
        for index in range(1, 13)
    ]

    actual_names = [
        str(item.get("filename"))
        for item in shards
    ]

    if actual_names != expected_names:
        raise HistoricalShardCaptureError(
            "SHARD_FILENAME_ORDER_MISMATCH"
        )

    expected_urls = [
        "https://data.sec.gov/submissions/" + name
        for name in expected_names
    ]

    actual_urls = [
        str(item.get("url"))
        for item in shards
    ]

    if actual_urls != expected_urls:
        raise HistoricalShardCaptureError(
            "SHARD_URL_SCOPE_MISMATCH"
        )

    return shards


def fetch_once(
    url: str,
    user_agent: str,
    timeout_seconds: int,
) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept-Encoding": "identity",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout_seconds,
    ) as response:
        payload = response.read()

        return (
            int(response.status),
            str(response.geturl()),
            payload,
        )


def capture_historical_shards(
    manifest: dict[str, Any],
    shards: list[dict[str, Any]],
    authorization: dict[str, Any],
    manifest_sha256: str,
    raw_root: str | Path,
    user_agent: str,
) -> dict[str, Any]:
    if authorization.get("network_capture_authorized") is not True:
        raise HistoricalShardCaptureError(
            "NETWORK_CAPTURE_NOT_AUTHORIZED"
        )

    if authorization.get("automatic_execution_authorized") is not False:
        raise HistoricalShardCaptureError(
            "AUTOMATIC_EXECUTION_MUST_REMAIN_FALSE"
        )

    if authorization.get("filing_header_capture_authorized") is not False:
        raise HistoricalShardCaptureError(
            "FILING_HEADER_CAPTURE_NOT_ALLOWED"
        )

    if authorization.get("filing_document_capture_authorized") is not False:
        raise HistoricalShardCaptureError(
            "FILING_DOCUMENT_CAPTURE_NOT_ALLOWED"
        )

    if authorization.get("full_215_execution_authorized") is not False:
        raise HistoricalShardCaptureError(
            "FULL_215_EXECUTION_NOT_ALLOWED"
        )

    if authorization.get("taxonomy_normalization_authorized") is not False:
        raise HistoricalShardCaptureError(
            "TAXONOMY_NORMALIZATION_NOT_ALLOWED"
        )

    if not user_agent or "@" not in user_agent:
        raise HistoricalShardCaptureError(
            "DECLARED_SEC_USER_AGENT_REQUIRED"
        )

    expected_manifest_sha = str(
        authorization.get(
            "manifest_sha256"
        )
        or ""
    )

    actual_manifest_sha = str(
        manifest_sha256
    )

    if actual_manifest_sha != expected_manifest_sha:
        raise HistoricalShardCaptureError(
            "AUTHORIZATION_MANIFEST_BINDING_MISMATCH"
        )

    maximum_requests = int(
        authorization[
            "execution_contract"
        ][
            "maximum_unique_sec_requests"
        ]
    )

    requests_per_second = int(
        authorization[
            "execution_contract"
        ][
            "maximum_requests_per_second"
        ]
    )

    retries = int(
        authorization[
            "execution_contract"
        ][
            "maximum_retry_attempts"
        ]
    )

    timeout_seconds = int(
        authorization[
            "execution_contract"
        ][
            "request_timeout_seconds"
        ]
    )

    if maximum_requests != 12:
        raise HistoricalShardCaptureError(
            "AUTHORIZATION_REQUEST_CEILING_MISMATCH"
        )

    if requests_per_second != 1:
        raise HistoricalShardCaptureError(
            "AUTHORIZATION_REQUEST_RATE_MISMATCH"
        )

    if retries != 0:
        raise HistoricalShardCaptureError(
            "AUTHORIZATION_RETRIES_MUST_BE_ZERO"
        )

    raw_root = Path(
        raw_root
    )

    raw_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    request_cache: dict[
        str,
        dict[str, Any],
    ] = {}

    records = []

    for shard in shards:
        url = str(
            shard[
                "url"
            ]
        )

        if url in request_cache:
            result = request_cache[
                url
            ]

        else:
            if len(request_cache) >= maximum_requests:
                raise RuntimeError(
                    "absolute SEC request ceiling exhausted "
                    "before next physical request"
                )

            if request_cache:
                time.sleep(
                    1.0
                    / float(
                        requests_per_second
                    )
                )

            status, final_url, payload = fetch_once(
                url,
                user_agent,
                timeout_seconds,
            )

            filename = str(
                shard[
                    "filename"
                ]
            )

            raw_path = (
                raw_root
                / filename
            )

            if raw_path.exists():
                raise HistoricalShardCaptureError(
                    "IMMUTABLE_RAW_FILE_ALREADY_EXISTS:"
                    + str(raw_path)
                )

            raw_path.write_bytes(
                payload
            )

            result = {
                "http_status": status,
                "final_url": final_url,
                "payload": payload,
                "raw_path": raw_path,
            }

            request_cache[
                url
            ] = result

        payload = result[
            "payload"
        ]

        json_valid = False
        accession_count = 0

        try:
            parsed = json.loads(
                payload.decode(
                    "utf-8-sig"
                )
            )

            if isinstance(
                parsed,
                dict,
            ):
                accession_count = len(
                    parsed.get(
                        "accessionNumber",
                        [],
                    )
                )

                json_valid = True

        except Exception:
            json_valid = False

        records.append(
            {
                "filename": shard["filename"],
                "url": url,
                "http_status": result["http_status"],
                "final_url": result["final_url"],
                "raw_path": str(
                    result[
                        "raw_path"
                    ]
                ),
                "payload_sha256": sha256_bytes(
                    payload
                ),
                "payload_bytes": len(
                    payload
                ),
                "json_valid": json_valid,
                "accession_count": accession_count,
                "filing_from": shard.get(
                    "filing_from"
                ),
                "filing_to": shard.get(
                    "filing_to"
                ),
                "filing_count_advertised": shard.get(
                    "filing_count"
                ),
            }
        )

    all_http_200 = all(
        int(record["http_status"]) == 200
        for record in records
    )

    all_json_valid = all(
        record["json_valid"] is True
        for record in records
    )

    return {
        "phase": "3.6b.3r",
        "route_type": (
            "SEC_SUBMISSIONS_ADVERTISED_HISTORICAL_SHARDS"
        ),
        "capture_complete": (
            len(records) == 12
            and all_http_200
            and all_json_valid
        ),
        "target_symbols": [
            "AAXJ",
            "ACWI",
            "IBTJ",
            "IWN",
        ],
        "historical_shard_count": 12,
        "captured_shard_count": len(
            records
        ),
        "request_count": len(
            request_cache
        ),
        "records": records,
        "all_http_200": all_http_200,
        "all_json_valid": all_json_valid,
        "filing_header_capture_authorized": False,
        "filing_document_capture_authorized": False,
        "full_priority_population_execution_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": (
            "OFFLINE_HISTORICAL_ACCESSION_REDUCTION"
        ),
    }


def write_outputs(
    ledger: dict[str, Any],
    output_path: str | Path,
    summary_path: str | Path,
) -> dict[str, Any]:
    output = Path(
        output_path
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = canonical_json_bytes(
        ledger
    )

    output.write_bytes(
        payload
    )

    summary = {
        key: value
        for key, value
        in ledger.items()
        if key != "records"
    }

    summary[
        "capture_ledger_sha256"
    ] = sha256_bytes(
        payload
    )

    summary_target = Path(
        summary_path
    )

    summary_target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_target.write_bytes(
        canonical_json_bytes(
            summary
        )
    )

    return summary
