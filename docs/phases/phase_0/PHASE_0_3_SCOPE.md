# Phase 0.3 — Contracts and Configuration Foundation

## Objective

Establish versioned native and UIP contract boundaries, stable security identity rules, governed configuration, compatibility controls, and fail-closed validation.

## In Scope

- Native security identity schema
- UIP package manifest schema
- Contract registry and semantic version policy
- Initial ETF universe configuration
- Stable identifiers independent of ticker
- Configuration and compatibility validation
- Contract regression tests
- Phase 0.3 certification

## Out of Scope

- Live provider ingestion
- Market price certification
- Forecasting or ranking
- Portfolio recommendations
- Certified UIP package publication
- Individual-stock production activation
- Automatic execution

## Acceptance Criteria

1. VOO, SCHD, and QQQM remain the exact initial ETF universe.
2. Every security has a stable `security_id`; ticker is not sufficient identity.
3. Unknown contracts fail closed.
4. Breaking changes require migration.
5. Major contract versions must match.
6. Schemas reject undeclared properties.
7. UIP package manifests explicitly prohibit automatic execution.
8. Individual-stock production remains unauthorized.
9. All prior regression tests remain active.
10. At least 24 tests execute and pass.
