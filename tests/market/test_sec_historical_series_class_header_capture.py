from __future__ import annotations

import copy
import json

import pytest

import foundation.market.sec_historical_series_class_header_capture as mod


def manifest():
    records = []

    data = [
        (
            "IWN",
            "S000004342",
            "C000012072",
            "0000950130-00-003430",
        ),
        (
            "IWN",
            "S000004342",
            "C000012072",
            "0000929624-00-001344",
        ),
        (
            "ACWI",
            "S000021461",
            "C000061364",
            "0001193125-08-065656",
        ),
        (
            "ACWI",
            "S000021461",
            "C000061364",
            "0000897436-08-000134",
        ),
        (
            "AAXJ",
            "S000022496",
            "C000065072",
            "0001193125-08-163862",
        ),
        (
            "AAXJ",
            "S000022496",
            "C000065072",
            "0000897436-08-000396",
        ),
        (
            "IBTJ",
            "S000067564",
            "C000217190",
            "0001193125-20-048487",
        ),
        (
            "IBTJ",
            "S000067564",
            "C000217190",
            "0001193125-20-049815",
        ),
    ]

    for sequence, (
        symbol,
        series_id,
        class_id,
        accession,
    ) in enumerate(
        data,
        start=1,
    ):
        flat = accession.replace(
            "-",
            "",
        )

        records.append(
            {
                "sequence": sequence,
                "security_id": (
                    "US-ETF-"
                    + symbol
                ),
                "symbol": symbol,
                "sec_cik": "0001100663",
                "sec_series_id": series_id,
                "sec_class_contract_id": class_id,
                "accession_number": accession,
                "accession_number_no_dashes": flat,
                "filing_date": "2020-01-01",
                "form": "497",
                "filing_index_url": (
                    "https://www.sec.gov/Archives/"
                    "edgar/data/1100663/"
                    + flat
                    + "/index.json"
                ),
            }
        )

    return {
        "phase": "3.6b.3s",
        "route_type": (
            "EXACT_HISTORICAL_ACCESSION_FILING_INDEX_PILOT"
        ),
        "target_symbols": [
            "IWN",
            "ACWI",
            "AAXJ",
            "IBTJ",
        ],
        "target_count": 4,
        "accession_count": 8,
        "records": records,
        "execution_contract": {
            "network_capture_authorized": False,
            "maximum_unique_sec_requests": 8,
            "maximum_requests_per_second": 1,
            "maximum_retry_attempts": 0,
            "cache_identical_requests": True,
            "immutable_raw_storage": True,
            "exact_manifest_urls_only": True,
        },
        "authority": {
            "historical_filing_index_capture_authorized": False,
            "historical_filing_document_capture_authorized": False,
            "full_215_execution_authorized": False,
            "taxonomy_evidence_normalization_authorized": False,
        },
    }


def authorization(manifest_sha):
    return {
        "manifest_sha256": manifest_sha,
        "network_capture_authorized": True,
        "historical_filing_index_capture_authorized": True,
        "historical_filing_document_capture_authorized": False,
        "additional_accession_discovery_authorized": False,
        "expanded_pilot_authorized": False,
        "full_215_execution_authorized": False,
        "taxonomy_normalization_authorized": False,
        "automatic_execution_authorized": False,
        "execution_contract": {
            "maximum_unique_sec_requests": 8,
            "maximum_requests_per_second": 1,
            "maximum_retry_attempts": 0,
            "request_timeout_seconds": 45,
        },
    }


def manifest_bytes(value):
    return (
        json.dumps(
            value,
            indent=2,
        )
        + "\n"
    ).encode(
        "utf-8"
    )


def test_validate_manifest_accepts_exact_scope():
    value = manifest()
    payload = manifest_bytes(
        value
    )

    records = mod.validate_manifest(
        value,
        mod.sha256_bytes(
            payload
        ),
        payload,
    )

    assert len(records) == 8


def test_validate_manifest_rejects_url_change():
    value = manifest()

    value[
        "records"
    ][0][
        "filing_index_url"
    ] = (
        "https://www.sec.gov/"
        "Archives/edgar/data/"
        "1100663/not-authorized/index.json"
    )

    payload = manifest_bytes(
        value
    )

    with pytest.raises(
        mod.HistoricalHeaderCaptureError,
        match="INDEX_URL_SCOPE_MISMATCH",
    ):
        mod.validate_manifest(
            value,
            mod.sha256_bytes(
                payload
            ),
            payload,
        )


def test_validate_manifest_rejects_self_authorized_network():
    value = manifest()

    value[
        "execution_contract"
    ][
        "network_capture_authorized"
    ] = True

    payload = manifest_bytes(
        value
    )

    with pytest.raises(
        mod.HistoricalHeaderCaptureError,
        match="MANIFEST_MUST_NOT_SELF_AUTHORIZE_NETWORK",
    ):
        mod.validate_manifest(
            value,
            mod.sha256_bytes(
                payload
            ),
            payload,
        )


def test_capture_requires_external_authorization():
    value = manifest()

    auth = authorization(
        "abc"
    )

    auth[
        "network_capture_authorized"
    ] = False

    with pytest.raises(
        mod.HistoricalHeaderCaptureError,
        match="NETWORK_CAPTURE_NOT_AUTHORIZED",
    ):
        mod.capture_historical_headers(
            value,
            value["records"],
            auth,
            "abc",
            "unused",
            "name@example.com",
        )


def test_capture_rejects_document_authority():
    value = manifest()

    auth = authorization(
        "abc"
    )

    auth[
        "historical_filing_document_capture_authorized"
    ] = True

    with pytest.raises(
        mod.HistoricalHeaderCaptureError,
        match="DOCUMENT_CAPTURE_NOT_ALLOWED",
    ):
        mod.capture_historical_headers(
            value,
            value["records"],
            auth,
            "abc",
            "unused",
            "name@example.com",
        )


def test_capture_exact_eight_indexes_only(
    tmp_path,
    monkeypatch,
):
    value = manifest()

    payload = manifest_bytes(
        value
    )

    manifest_sha = (
        mod.sha256_bytes(
            payload
        )
    )

    auth = authorization(
        manifest_sha
    )

    calls = []

    def fake_fetch(
        url,
        user_agent,
        timeout_seconds,
    ):
        calls.append(
            url
        )

        body = json.dumps(
            {
                "directory": {
                    "item": [
                        {
                            "name": (
                                "primary.htm"
                            )
                        }
                    ]
                }
            }
        ).encode(
            "utf-8"
        )

        return (
            200,
            url,
            body,
        )

    monkeypatch.setattr(
        mod,
        "fetch_once",
        fake_fetch,
    )

    monkeypatch.setattr(
        mod.time,
        "sleep",
        lambda _: None,
    )

    ledger = (
        mod.capture_historical_headers(
            value,
            value["records"],
            auth,
            manifest_sha,
            tmp_path,
            "name@example.com",
        )
    )

    assert ledger[
        "capture_complete"
    ] is True

    assert ledger[
        "request_count"
    ] == 8

    assert len(
        calls
    ) == 8

    assert all(
        url.endswith(
            "/index.json"
        )
        for url in calls
    )

    assert ledger[
        "historical_filing_document_capture_authorized"
    ] is False

    assert ledger[
        "full_215_execution_authorized"
    ] is False

    assert ledger[
        "taxonomy_evidence_normalization_authorized"
    ] is False


def test_index_identity_requires_series_and_class():
    record = {
        "symbol": "ACWI",
        "sec_cik": "0001100663",
        "sec_series_id": "S000021461",
        "sec_class_contract_id": "C000061364",
    }

    full = (
        b"S000021461 C000061364 "
        b"ACWI 0001100663"
    )

    partial = (
        b"S000021461 ACWI "
        b"0001100663"
    )

    full_result = (
        mod.evaluate_index_identity(
            record,
            full,
        )
    )

    partial_result = (
        mod.evaluate_index_identity(
            record,
            partial,
        )
    )

    assert full_result[
        "structural_series_class_match"
    ] is True

    assert partial_result[
        "structural_series_class_match"
    ] is False
