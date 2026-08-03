# Phase 0.4 — Source Authority and Data-Zone Foundation

## Purpose

Establish the governed source hierarchy and storage-zone controls required before any market data may become an analytical input.

## In Scope

- five ordered source-authority tiers
- explicit allowed uses by source tier
- unknown-source blocking
- raw, staged, curated, evidence, and quarantine zones
- immutable raw and evidence zones
- required observation and ingestion timestamps
- stable source-record identity and SHA-256 evidence
- deterministic freshness states
- preservation and quarantine of conflicting observations
- restricted and licensed data boundaries

## Acceptance Criteria

1. All prior Phase 0.1–0.3 regression tests remain green.
2. Eight Phase 0.4 source and data-zone tests pass.
3. The complete suite executes at least 32 tests.
4. Unknown sources fail closed.
5. Raw source captures cannot be overwritten.
6. Source conflicts are preserved and cannot be silently resolved.
7. Missing or invalid lineage blocks validation.
8. Research-only sources cannot become certified inputs.
9. Licensed data requires an explicit license review and remains outside Git.
10. Certification produces no critical failures.

## Authority Boundary

Phase 0.4 authorizes source-governance development, data-zone development, lineage validation, and research-only development. It does not authorize certified market monitoring, forecasts, portfolio actions, contribution allocations, UIP export, or automatic execution.
