# Platform Authority Boundary

## Purpose

This standard defines the separation of authority between the Stocks and ETF
Intelligence Platform, the Universal Investment Platform, and the platform owner.

## Domain Platform Authority

The Stocks and ETF Intelligence Platform may:

- Collect approved public-market evidence
- Preserve raw evidence and source lineage
- Reconcile conflicting sources through governed rules
- Calculate domain-native analytics
- Produce research, shadow, provisional, and certified outputs
- Recommend actions within the approved stocks and ETF domain budget
- Produce immutable export packages for UIP validation

## UIP Authority

The Universal Investment Platform may:

- Validate exported contracts and manifests
- Reject incomplete, incompatible, stale, or uncertified packages
- Import complete packages transactionally
- Compare stocks and ETF opportunities with other investment domains
- Apply total-portfolio risk constraints
- Modify or reject domain allocation recommendations during cross-asset analysis

## Owner Authority

Only Devon Lockard may authorize:

- Initial provisional production use
- Initial full production use
- Expansion of the approved investment universe
- Activation of paid data providers
- Activation of individual-stock production analysis
- Actual purchases, sales, transfers, or brokerage actions

## Explicit Prohibitions

The domain platform shall never:

1. Write directly to UIP production tables.
2. Assume package generation means UIP import acceptance.
3. Execute or submit brokerage orders.
4. Use research-only evidence as sole support for a certified recommendation.
5. Silence unresolved decision-critical source conflicts.
6. Change approved policy or model weights without versioning.
7. Modify certified export packages in place.
8. Use future information in historical validation.
9. Treat a ticker as the sole permanent security identifier.
10. Enable automatic trade execution under the current charter.

## Enforcement

Violations of this authority boundary are critical certification failures and
must block the affected production authority.
