from __future__ import annotations

import unittest
from pathlib import Path

from foundation.validation.sources import (
    SourceValidationError,
    freshness_state,
    load_governed_source_controls,
    sha256_text,
    validate_data_zones,
    validate_lineage,
    validate_source_authority,
)

ROOT = Path(__file__).resolve().parents[2]


class Phase04SourceAuthorityTests(unittest.TestCase):
    def test_source_authority_is_fail_closed(self) -> None:
        authority, _ = load_governed_source_controls(ROOT)
        self.assertTrue(authority["unknown_sources_blocked"])
        self.assertTrue(authority["source_conflicts_preserved"])
        self.assertTrue(authority["silent_conflict_resolution_forbidden"])

    def test_source_tiers_are_complete_and_ordered(self) -> None:
        authority, _ = load_governed_source_controls(ROOT)
        self.assertEqual([item["tier"] for item in authority["tiers"]], [1, 2, 3, 4, 5])
        self.assertEqual(authority["tiers"][-1]["allowed_uses"], ["research"])

    def test_restricted_data_stays_outside_git(self) -> None:
        authority, _ = load_governed_source_controls(ROOT)
        self.assertTrue(authority["restricted_data_must_remain_outside_git"])
        licensed = next(item for item in authority["tiers"] if item["id"] == "LICENSED_PRIMARY")
        self.assertTrue(licensed["requires_license_review"])

    def test_required_data_zones_and_immutability(self) -> None:
        _, zones = load_governed_source_controls(ROOT)
        self.assertEqual([item["id"] for item in zones["zones"]], ["raw", "staged", "curated", "evidence", "quarantine"])
        immutable = {item["id"] for item in zones["zones"] if not item["mutable"]}
        self.assertEqual(immutable, {"raw", "evidence"})

    def test_lineage_requires_all_fields_and_valid_sha(self) -> None:
        _, zones = load_governed_source_controls(ROOT)
        record = {
            "source_id": "sec_edgar",
            "source_tier": "OFFICIAL_PRIMARY",
            "observed_at_utc": "2026-08-03T12:00:00Z",
            "ingested_at_utc": "2026-08-03T12:05:00Z",
            "source_record_id": "abc-123",
            "content_sha256": sha256_text("payload"),
        }
        validate_lineage(record, zones["required_lineage_fields"])
        with self.assertRaises(SourceValidationError):
            validate_lineage({**record, "content_sha256": "bad"}, zones["required_lineage_fields"])

    def test_future_observation_is_rejected(self) -> None:
        _, zones = load_governed_source_controls(ROOT)
        record = {
            "source_id": "source",
            "source_tier": "PUBLIC_SECONDARY",
            "observed_at_utc": "2026-08-03T13:00:00Z",
            "ingested_at_utc": "2026-08-03T12:00:00Z",
            "source_record_id": "row-1",
            "content_sha256": sha256_text("row"),
        }
        with self.assertRaises(SourceValidationError):
            validate_lineage(record, zones["required_lineage_fields"])

    def test_freshness_states_are_deterministic(self) -> None:
        self.assertEqual(freshness_state("2026-08-03T10:00:00Z", "2026-08-03T12:00:00Z", 4, 24), "CURRENT")
        self.assertEqual(freshness_state("2026-08-03T06:00:00Z", "2026-08-03T12:00:00Z", 4, 24), "AGING")
        self.assertEqual(freshness_state("2026-08-01T12:00:00Z", "2026-08-03T12:00:00Z", 4, 24), "STALE")
        self.assertEqual(freshness_state("invalid", "2026-08-03T12:00:00Z", 4, 24), "UNKNOWN")

    def test_controls_reject_authority_or_zone_weakening(self) -> None:
        authority, zones = load_governed_source_controls(ROOT)
        with self.assertRaises(SourceValidationError):
            validate_source_authority({**authority, "unknown_sources_blocked": False})
        weakened = {**zones, "zones": [{**item, "mutable": True} if item["id"] == "raw" else item for item in zones["zones"]]}
        with self.assertRaises(SourceValidationError):
            validate_data_zones(weakened)


if __name__ == "__main__":
    unittest.main()
