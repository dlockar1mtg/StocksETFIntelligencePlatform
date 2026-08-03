from __future__ import annotations

import json
import unittest
from pathlib import Path

from foundation.validation.contracts import (
    ContractValidationError,
    load_json,
    validate_contract_registry,
    validate_initial_universe,
    validate_security_identity,
    versions_compatible,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase03ContractsConfigurationTests(unittest.TestCase):
    def test_contract_registry_is_fail_closed(self) -> None:
        registry = load_json(ROOT / "config/contracts/contract_registry.json")
        validate_contract_registry(registry)
        self.assertTrue(registry["unknown_contracts_blocked"])
        self.assertTrue(registry["breaking_changes_require_migration"])

    def test_required_contracts_are_registered(self) -> None:
        registry = load_json(ROOT / "config/contracts/contract_registry.json")
        ids = {item["contract_id"] for item in registry["contracts"]}
        self.assertEqual(ids, {"native.security_identity", "uip.package_manifest"})

    def test_registered_schema_paths_exist(self) -> None:
        registry = load_json(ROOT / "config/contracts/contract_registry.json")
        for item in registry["contracts"]:
            self.assertTrue((ROOT / item["schema"]).is_file())

    def test_schema_documents_are_valid_json_objects(self) -> None:
        for relative in ["contracts/native/security_identity.schema.json", "contracts/uip/package_manifest.schema.json"]:
            document = load_json(ROOT / relative)
            self.assertEqual(document["type"], "object")
            self.assertFalse(document["additionalProperties"])

    def test_stable_security_identity_is_not_ticker_only(self) -> None:
        record = {"security_id": "SEC-US-VOO", "asset_type": "ETF", "ticker": "VOO", "exchange": "ARCX", "currency": "USD", "identity_status": "PROVISIONAL"}
        validate_security_identity(record)
        with self.assertRaises(ContractValidationError):
            validate_security_identity({"security_id": "VOO", "asset_type": "ETF", "ticker": "VOO", "exchange": "ARCX", "currency": "USD", "identity_status": "PROVISIONAL"})

    def test_initial_universe_is_exact_and_stock_production_blocked(self) -> None:
        universe = load_json(ROOT / "config/universe/initial_etf_universe.json")
        validate_initial_universe(universe)
        self.assertEqual([item["ticker"] for item in universe["securities"]], ["VOO", "SCHD", "QQQM"])
        self.assertFalse(universe["individual_stock_production_authorized"])

    def test_major_version_compatibility(self) -> None:
        self.assertTrue(versions_compatible("1.2.0", "1.9.9"))
        self.assertFalse(versions_compatible("1.2.0", "2.0.0"))
        with self.assertRaises(ContractValidationError):
            versions_compatible("not-semver", "1.0.0")

    def test_uip_manifest_forbids_automatic_execution(self) -> None:
        schema = load_json(ROOT / "contracts/uip/package_manifest.schema.json")
        self.assertEqual(schema["properties"]["automatic_execution_authorized"], {"const": False})


if __name__ == "__main__":
    unittest.main()
