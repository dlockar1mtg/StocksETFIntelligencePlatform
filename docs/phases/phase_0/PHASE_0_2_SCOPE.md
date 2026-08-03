# Phase 0.2 — Repository Foundation

## Objective

Establish the governed, testable, ETF-first and stock-ready repository foundation without granting analytical or production decision authority.

## Deliverables

- Python project configuration
- Layered foundation package
- Machine-readable repository architecture
- Environment validator
- Repository and governance regression tests
- GitHub Actions CI baseline
- Fail-closed Phase 0.2 certification runner
- One-command PowerShell certification entry point

## Required Layers

- `foundation/domain`
- `foundation/infrastructure`
- `foundation/applications`
- `foundation/validation`
- `foundation/integration`

Domain logic shall remain independent of provider clients, local filesystem paths, brokerage execution, and UIP production storage.

## Acceptance Criteria

1. Phase 0.1 governance regression tests remain passing.
2. Phase 0.2 repository regression tests pass.
3. The environment validator passes on supported Python.
4. CI runs environment validation, the complete regression suite, and certification.
5. At least 16 tests execute during Phase 0.2 certification.
6. Automatic execution remains prohibited.
7. Direct UIP production writes remain prohibited.
8. Certified recommendations and exports remain unauthorized.
9. The working tree remains clean after generated artifacts are ignored.

## Authorized Scope

Phase 0.2 authorizes repository scaffolding, contract development, governance validation, and research-only development.

It does not authorize certified market monitoring, forecasting, ranking, portfolio action, contribution allocation, UIP export, or trade execution.
