# Phase 0.6 — Calendar, Benchmark, and Corporate-Action Standards

## Objective

Establish fail-closed market calendar, return-comparison, and corporate-action standards before any certified analytics are developed.

## In scope

- governed US market calendar controls
- America/New_York session authority
- explicit holiday and early-close records
- total-return security and benchmark comparisons
- distribution reinvestment and split adjustment rules
- 252-trading-day annualization
- supported ETF corporate actions
- point-in-time announcement and effective-date enforcement
- conflict quarantine and evidence-backed manual overrides
- Phase 0.6 regression tests and certification

## Out of scope

- live market collection
- certified return calculation
- asset outlooks
- portfolio actions
- contribution allocation
- UIP export certification
- automatic execution

## Acceptance criteria

1. All governed Phase 0.6 JSON controls parse successfully.
2. Unknown calendar dates and corporate actions fail closed.
3. Certified security and benchmark comparisons require total-return bases.
4. Look-ahead corporate-action use is rejected.
5. All Phase 0.1 through Phase 0.6 regression tests pass.
6. At least 48 tests execute.
7. The certification report contains no critical failures.
