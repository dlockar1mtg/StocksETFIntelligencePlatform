from __future__ import annotations

import json
from pathlib import Path

import pytest

from foundation.market.corrected_sec_route_discovery_pilot_execution_authorization import (
    CorrectedPilotAuthorizationError,
    build_authorization,
)


ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = (
    ROOT
    / "artifacts"
    / "analysis"
    / "phase_3_model_taxonomy_production"
    / "2026-08-08"
    / "corrected_route_discovery_pilot"
    / "corrected_sec_route_discovery_pilot_manifest.json"
)

POLICY_PATH = (
    ROOT
    / "config"
    / "market"
    / "corrected_sec_route_discovery_pilot_execution_authorization_policy.json"
)

GOVERNED_HEAD = (
    "9b1697b5776fa766939ef6e04e5d20162bc9052f"
)


def load(path: Path) -> dict:
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def build() -> dict:
    manifest_bytes = (
        MANIFEST_PATH.read_bytes()
    )

    return build_authorization(
        load(MANIFEST_PATH),
        manifest_bytes,
        load(POLICY_PATH),
        GOVERNED_HEAD,
    )


def test_authorization_exact_five_symbols() -> None:
    authorization = build()

    assert (
        authorization["authorized_symbols"]
        == [
            "AAXJ",
            "ACWI",
            "IBTJ",
            "IWN",
            "VLUE",
        ]
    )

    assert (
        authorization[
            "authorized_record_count"
        ]
        == 5
    )


def test_authorization_exact_manifest_hash() -> None:
    authorization = build()

    assert (
        authorization[
            "pilot_manifest_sha256"
        ]
        == (
            "ee4e0880b2d3e0b42bc64d686fe30d8659d04b3919dae9c608232e2adfb94fa9"
        )
    )


def test_authorization_is_strictly_bounded() -> None:
    authorization = build()

    contract = (
        authorization[
            "execution_contract"
        ]
    )

    assert (
        contract[
            "maximum_candidate_documents_per_security"
        ]
        == 5
    )

    assert (
        contract[
            "maximum_total_sec_requests"
        ]
        == 30
    )

    assert (
        contract[
            "maximum_requests_per_second"
        ]
        == 1
    )

    assert (
        authorization[
            "network_capture_authorized"
        ]
        is True
    )

    assert (
        authorization[
            "automatic_execution_authorized"
        ]
        is False
    )

    assert (
        authorization[
            "full_215_execution_authorized"
        ]
        is False
    )

    assert (
        authorization[
            "taxonomy_normalization_authorized"
        ]
        is False
    )


def test_manifest_hash_drift_fails_closed() -> None:
    manifest = load(
        MANIFEST_PATH
    )

    manifest["records"][0][
        "symbol"
    ] = "DRIFT"

    drifted_bytes = (
        json.dumps(
            manifest,
            indent=2,
        ).encode(
            "utf-8"
        )
    )

    with pytest.raises(
        CorrectedPilotAuthorizationError
    ):
        build_authorization(
            manifest,
            drifted_bytes,
            load(POLICY_PATH),
            GOVERNED_HEAD,
        )


def test_governed_head_drift_fails_closed() -> None:
    with pytest.raises(
        CorrectedPilotAuthorizationError
    ):
        build_authorization(
            load(MANIFEST_PATH),
            MANIFEST_PATH.read_bytes(),
            load(POLICY_PATH),
            "WRONG_HEAD",
        )


def test_manifest_itself_remains_non_authorizing() -> None:
    manifest = load(
        MANIFEST_PATH
    )

    assert (
        manifest[
            "network_execution_authorized"
        ]
        is False
    )
