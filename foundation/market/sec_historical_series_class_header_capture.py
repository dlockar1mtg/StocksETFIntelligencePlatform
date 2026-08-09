from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


class HistoricalHeaderCaptureError(ValueError):
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
        raise HistoricalHeaderCaptureError(
            "JSON_OBJECT_REQUIRED"
        )

    return value


def validate_manifest(
    manifest: dict[str, Any],
    expected_manifest_sha256: str,
    manifest_bytes: bytes,
) -> list[dict[str, Any]]:

    if sha256_bytes(manifest_bytes) != expected_manifest_sha256:
        raise HistoricalHeaderCaptureError(
            "MANIFEST_SHA256_MISMATCH"
        )

    if manifest.get("phase") != "3.6b.3s":
        raise HistoricalHeaderCaptureError(
            "PHASE_MISMATCH"
        )

    if manifest.get("route_type") != (
        "EXACT_HISTORICAL_ACCESSION_FILING_INDEX_PILOT"
    ):
        raise HistoricalHeaderCaptureError(
            "ROUTE_TYPE_MISMATCH"
        )

    if manifest.get("target_symbols") != [
        "IWN",
        "ACWI",
        "AAXJ",
        "IBTJ",
    ]:
        raise HistoricalHeaderCaptureError(
            "TARGET_SCOPE_MISMATCH"
        )

    if int(manifest.get("target_count", -1)) != 4:
        raise HistoricalHeaderCaptureError(
            "TARGET_COUNT_MISMATCH"
        )

    if int(manifest.get("accession_count", -1)) != 8:
        raise HistoricalHeaderCaptureError(
            "ACCESSION_COUNT_MISMATCH"
        )

    execution = manifest[
        "execution_contract"
    ]

    if execution["network_capture_authorized"] is not False:
        raise HistoricalHeaderCaptureError(
            "MANIFEST_MUST_NOT_SELF_AUTHORIZE_NETWORK"
        )

    if int(
        execution[
            "maximum_unique_sec_requests"
        ]
    ) != 8:
        raise HistoricalHeaderCaptureError(
            "REQUEST_CEILING_MISMATCH"
        )

    if int(
        execution[
            "maximum_requests_per_second"
        ]
    ) != 1:
        raise HistoricalHeaderCaptureError(
            "REQUEST_RATE_MISMATCH"
        )

    if int(
        execution[
            "maximum_retry_attempts"
        ]
    ) != 0:
        raise HistoricalHeaderCaptureError(
            "RETRIES_MUST_BE_ZERO"
        )

    if execution[
        "cache_identical_requests"
    ] is not True:
        raise HistoricalHeaderCaptureError(
            "REQUEST_CACHE_REQUIRED"
        )

    if execution[
        "immutable_raw_storage"
    ] is not True:
        raise HistoricalHeaderCaptureError(
            "IMMUTABLE_STORAGE_REQUIRED"
        )

    if execution[
        "exact_manifest_urls_only"
    ] is not True:
        raise HistoricalHeaderCaptureError(
            "EXACT_MANIFEST_URL_SCOPE_REQUIRED"
        )

    authority = manifest[
        "authority"
    ]

    if authority[
        "historical_filing_index_capture_authorized"
    ] is not False:
        raise HistoricalHeaderCaptureError(
            "MANIFEST_INDEX_CAPTURE_MUST_REMAIN_FALSE"
        )

    if authority[
        "historical_filing_document_capture_authorized"
    ] is not False:
        raise HistoricalHeaderCaptureError(
            "MANIFEST_DOCUMENT_CAPTURE_MUST_REMAIN_FALSE"
        )

    if authority[
        "full_215_execution_authorized"
    ] is not False:
        raise HistoricalHeaderCaptureError(
            "FULL_215_EXECUTION_MUST_REMAIN_FALSE"
        )

    if authority[
        "taxonomy_evidence_normalization_authorized"
    ] is not False:
        raise HistoricalHeaderCaptureError(
            "TAXONOMY_NORMALIZATION_MUST_REMAIN_FALSE"
        )

    records = list(
        manifest.get(
            "records",
            [],
        )
    )

    if len(records) != 8:
        raise HistoricalHeaderCaptureError(
            "EXPECTED_8_MANIFEST_RECORDS"
        )

    expected_sequences = list(
        range(1, 9)
    )

    actual_sequences = [
        int(record.get("sequence", -1))
        for record in records
    ]

    if actual_sequences != expected_sequences:
        raise HistoricalHeaderCaptureError(
            "SEQUENCE_ORDER_MISMATCH"
        )

    accessions = [
        str(
            record.get(
                "accession_number",
                ""
            )
        )
        for record in records
    ]

    if len(set(accessions)) != 8:
        raise HistoricalHeaderCaptureError(
            "DUPLICATE_ACCESSION"
        )

    for record in records:

        accession = str(
            record[
                "accession_number"
            ]
        )

        flat = accession.replace(
            "-",
            "",
        )

        if str(
            record[
                "accession_number_no_dashes"
            ]
        ) != flat:
            raise HistoricalHeaderCaptureError(
                "ACCESSION_FLAT_MISMATCH"
            )

        expected_url = (
            "https://www.sec.gov/Archives/edgar/data/"
            "1100663/"
            + flat
            + "/index.json"
        )

        if str(
            record[
                "filing_index_url"
            ]
        ) != expected_url:
            raise HistoricalHeaderCaptureError(
                "INDEX_URL_SCOPE_MISMATCH"
            )

    return records


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

        return (
            int(response.status),
            str(response.geturl()),
            response.read(),
        )


def evaluate_index_identity(
    record: dict[str, Any],
    payload: bytes,
) -> dict[str, Any]:

    text = payload.decode(
        "utf-8",
        errors="ignore",
    ).lower()

    series_id = str(
        record.get(
            "sec_series_id",
            "",
        )
    ).strip().lower()

    class_id = str(
        record.get(
            "sec_class_contract_id",
            "",
        )
    ).strip().lower()

    symbol = str(
        record.get(
            "symbol",
            "",
        )
    ).strip().lower()

    cik = str(
        record.get(
            "sec_cik",
            "",
        )
    ).strip().lower()

    cik_unpadded = (
        cik.lstrip("0")
        if cik
        else ""
    )

    markers = {
        "sec_series_id": (
            bool(series_id)
            and series_id in text
        ),
        "sec_class_contract_id": (
            bool(class_id)
            and class_id in text
        ),
        "symbol": (
            bool(symbol)
            and symbol in text
        ),
        "sec_cik": (
            bool(cik)
            and (
                cik in text
                or (
                    bool(cik_unpadded)
                    and cik_unpadded in text
                )
            )
        ),
    }

    structural_identity = (
        markers[
            "sec_series_id"
        ]
        and markers[
            "sec_class_contract_id"
        ]
    )

    return {
        "identity_markers": markers,
        "structural_series_class_match": bool(
            structural_identity
        ),
    }


def capture_historical_headers(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    authorization: dict[str, Any],
    manifest_sha256: str,
    raw_root: str | Path,
    user_agent: str,
) -> dict[str, Any]:

    if authorization.get(
        "network_capture_authorized"
    ) is not True:
        raise HistoricalHeaderCaptureError(
            "NETWORK_CAPTURE_NOT_AUTHORIZED"
        )

    if authorization.get(
        "historical_filing_index_capture_authorized"
    ) is not True:
        raise HistoricalHeaderCaptureError(
            "INDEX_CAPTURE_NOT_AUTHORIZED"
        )

    if authorization.get(
        "historical_filing_document_capture_authorized"
    ) is not False:
        raise HistoricalHeaderCaptureError(
            "DOCUMENT_CAPTURE_NOT_ALLOWED"
        )

    if authorization.get(
        "additional_accession_discovery_authorized"
    ) is not False:
        raise HistoricalHeaderCaptureError(
            "ADDITIONAL_ACCESSION_DISCOVERY_NOT_ALLOWED"
        )

    if authorization.get(
        "expanded_pilot_authorized"
    ) is not False:
        raise HistoricalHeaderCaptureError(
            "EXPANDED_PILOT_NOT_ALLOWED"
        )

    if authorization.get(
        "full_215_execution_authorized"
    ) is not False:
        raise HistoricalHeaderCaptureError(
            "FULL_215_EXECUTION_NOT_ALLOWED"
        )

    if authorization.get(
        "taxonomy_normalization_authorized"
    ) is not False:
        raise HistoricalHeaderCaptureError(
            "TAXONOMY_NORMALIZATION_NOT_ALLOWED"
        )

    if authorization.get(
        "automatic_execution_authorized"
    ) is not False:
        raise HistoricalHeaderCaptureError(
            "AUTOMATIC_EXECUTION_MUST_REMAIN_FALSE"
        )

    if not user_agent or "@" not in user_agent:
        raise HistoricalHeaderCaptureError(
            "DECLARED_SEC_USER_AGENT_REQUIRED"
        )

    expected_manifest_sha = str(
        authorization.get(
            "manifest_sha256",
            "",
        )
    )

    if manifest_sha256 != expected_manifest_sha:
        raise HistoricalHeaderCaptureError(
            "AUTHORIZATION_MANIFEST_BINDING_MISMATCH"
        )

    execution = authorization[
        "execution_contract"
    ]

    maximum_requests = int(
        execution[
            "maximum_unique_sec_requests"
        ]
    )

    requests_per_second = int(
        execution[
            "maximum_requests_per_second"
        ]
    )

    retries = int(
        execution[
            "maximum_retry_attempts"
        ]
    )

    timeout_seconds = int(
        execution[
            "request_timeout_seconds"
        ]
    )

    if maximum_requests != 8:
        raise HistoricalHeaderCaptureError(
            "AUTHORIZATION_REQUEST_CEILING_MISMATCH"
        )

    if requests_per_second != 1:
        raise HistoricalHeaderCaptureError(
            "AUTHORIZATION_REQUEST_RATE_MISMATCH"
        )

    if retries != 0:
        raise HistoricalHeaderCaptureError(
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

    output_records = []

    for source in records:

        url = str(
            source[
                "filing_index_url"
            ]
        )

        if url in request_cache:

            result = request_cache[
                url
            ]

        else:

            if len(
                request_cache
            ) >= maximum_requests:
                raise HistoricalHeaderCaptureError(
                    "ABSOLUTE_SEC_REQUEST_CEILING_EXHAUSTED"
                )

            if request_cache:
                time.sleep(
                    1.0
                    / float(
                        requests_per_second
                    )
                )

            status, final_url, payload = (
                fetch_once(
                    url,
                    user_agent,
                    timeout_seconds,
                )
            )

            raw_path = (
                raw_root
                / str(
                    source[
                        "symbol"
                    ]
                )
                / (
                    str(
                        source[
                            "accession_number_no_dashes"
                        ]
                    )
                    + "_index.json"
                )
            )

            raw_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if raw_path.exists():
                raise HistoricalHeaderCaptureError(
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
        document_names: list[str] = []

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
                json_valid = True

                items = parsed.get(
                    "directory",
                    {},
                ).get(
                    "item",
                    [],
                )

                if isinstance(
                    items,
                    list,
                ):
                    document_names = [
                        str(
                            item.get(
                                "name",
                                "",
                            )
                        )
                        for item in items
                        if isinstance(
                            item,
                            dict,
                        )
                        and item.get(
                            "name"
                        )
                    ]

        except Exception:
            json_valid = False

        identity = (
            evaluate_index_identity(
                source,
                payload,
            )
        )

        output_records.append(
            {
                "sequence": source[
                    "sequence"
                ],
                "security_id": source[
                    "security_id"
                ],
                "symbol": source[
                    "symbol"
                ],
                "sec_cik": source[
                    "sec_cik"
                ],
                "sec_series_id": source[
                    "sec_series_id"
                ],
                "sec_class_contract_id": source[
                    "sec_class_contract_id"
                ],
                "accession_number": source[
                    "accession_number"
                ],
                "filing_date": source[
                    "filing_date"
                ],
                "form": source[
                    "form"
                ],
                "filing_index_url": url,
                "http_status": result[
                    "http_status"
                ],
                "final_url": result[
                    "final_url"
                ],
                "payload_sha256": sha256_bytes(
                    payload
                ),
                "payload_bytes": len(
                    payload
                ),
                "raw_path": str(
                    result[
                        "raw_path"
                    ]
                ),
                "json_valid": json_valid,
                "document_count": len(
                    document_names
                ),
                "document_names": document_names,
                **identity,
            }
        )

    all_http_200 = all(
        int(
            record[
                "http_status"
            ]
        ) == 200
        for record in output_records
    )

    all_json_valid = all(
        record[
            "json_valid"
        ] is True
        for record in output_records
    )

    return {
        "phase": "3.6b.3s",
        "route_type": (
            "EXACT_HISTORICAL_ACCESSION_FILING_INDEX_PILOT"
        ),
        "capture_complete": (
            len(output_records) == 8
            and all_http_200
            and all_json_valid
        ),
        "target_symbols": [
            "IWN",
            "ACWI",
            "AAXJ",
            "IBTJ",
        ],
        "target_count": 4,
        "accession_count": 8,
        "captured_index_count": len(
            output_records
        ),
        "request_count": len(
            request_cache
        ),
        "all_http_200": all_http_200,
        "all_json_valid": all_json_valid,
        "records": output_records,
        "historical_filing_document_capture_authorized": False,
        "expanded_pilot_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_evidence_normalization_authorized": False,
        "production_taxonomy_classification_authorized": False,
        "next_required_step": (
            "OFFLINE_HISTORICAL_INDEX_IDENTITY_REVIEW"
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

    target = Path(
        summary_path
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_bytes(
        canonical_json_bytes(
            summary
        )
    )

    return summary
