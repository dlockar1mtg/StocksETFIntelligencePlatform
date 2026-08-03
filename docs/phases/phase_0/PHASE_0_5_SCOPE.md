# Phase 0.5 — Security Master and ETF Universe Foundation

## Objective

Establish governed, stable instrument identity and a fail-closed ETF universe before any market, analytics, forecast, ranking, or recommendation workflow is authorized.

## Included

- stable security identifiers for VOO, SCHD, and QQQM
- issuer, fund, share-class, exchange, currency, and benchmark identity
- governed lifecycle states
- benchmark registry and total-return benchmark identity
- exact Tier 1 ETF universe policy
- lifecycle and eligibility validation
- unknown-security and ticker-only identity blocking
- regression and certification controls

## Acceptance Criteria

1. All 40 regression tests pass.
2. Every governed ETF resolves through stable identity and supporting registries.
3. Unknown securities and benchmarks fail closed.
4. Delisted, liquidated, inactive, or incomplete records are ineligible.
5. Individual-stock production remains unauthorized.
6. Phase 0.5 certification contains no critical failures.

## Authority Boundary

Phase 0.5 authorizes security-master development, universe-governance development, eligibility validation, and research-only development. It does not authorize certified market monitoring, asset outlooks, portfolio actions, contribution allocations, UIP exports, or automatic execution.
