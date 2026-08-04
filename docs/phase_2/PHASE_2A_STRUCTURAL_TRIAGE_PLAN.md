# Phase 2A — ETF Structural Triage and Data-Cost Funnel

## Purpose

Phase 2A reduces downstream collection and analytical cost without imposing a predetermined universe size. The full exchange-discovery and broker-eligibility evidence remains preserved. Each ETF receives an evidence-based state and data-cost tier.

## Governing principle

The universe may resolve to 10, 100, 1,000, or more securities. No target count, quota, percentile, or arbitrary top-N rule may override the evidence gates.

## Funnel

1. **TIER_0_REFERENCE** — identity, listing, and broker status for the complete discovery universe.
2. **TIER_1_STRUCTURAL** — official metadata, structure, inception, benchmark, expenses, AUM, fund status, and specialized-product flags.
3. **TIER_2_MARKET_SCREEN** — recent price/volume, spreads, staleness, history depth, and corporate-action anomalies.
4. **TIER_3_COMPARATIVE_ANALYTICS** — complete returns, distributions, benchmark evidence, holdings, fundamentals, and overlap for data-qualified peer representatives and unique strategies.
5. **TIER_4_APPROVED** — highest-frequency monitoring and future forecast/recommendation inputs only for portfolio and explicitly approved candidates.

## Structural triage states

- `STRUCTURAL_CANDIDATE`
- `DATA_COLLECTION_CANDIDATE`
- `ANALYTICS_PROVISIONAL`
- `SPECIALIZED`
- `PORTFOLIO_RESTRICTED`
- `RESEARCH_ONLY`
- `QUARANTINED`
- `BLOCKED`

## Evidence sequence

### 2A.1 — Contract and governance baseline

Define the triage policy, record contract, validation rules, cost tiers, reason codes, and certification boundary.

### 2A.2 — Official structural metadata collection

Collect field-level authoritative evidence for fund identity, issuer, instrument structure, inception, strategy, benchmark, expense ratio, AUM, specialized flags, and closure/liquidation status. Preserve raw evidence and hashes outside Git.

### 2A.3 — Preliminary market screen

Collect a bounded recent market window sufficient to evaluate liquidity, spreads, stale pricing, zero-volume frequency, data continuity, history start, and corporate-action anomalies.

### 2A.4 — Strategy and peer grouping

Create governed peer groups using strategy, benchmark, asset class, geography, market-cap segment, factor, income approach, active/passive status, and specialized structure. Redundancy may reduce collection priority but cannot delete evidence or independently block a fund.

### 2A.5 — Evidence-derived triage snapshot

Produce an immutable dated snapshot containing each ETF's state, cost tier, reason codes, source lineage, conflicts, and authorized next collection step. Counts must emerge from the evidence and reconcile to the preserved discovery universe.

## Promotion controls

Promotion requires the applicable combination of:

- complete stable identity;
- active broker eligibility;
- admissible or explicitly specialized structure;
- adequate evidence authority and freshness;
- no unresolved decision-critical conflict;
- adequate history for the requested analytical use;
- sufficient liquidity and tradability for the intended portfolio role;
- benchmark and strategy identity;
- holdings transparency when required for look-through analytics;
- explicit owner approval before approved-candidate or portfolio recommendation authority.

## Prohibitions

Phase 2A does not authorize production analytics, forecasting, ranking, recommendations, contribution allocation, UIP export, direct UIP database writes, or automatic execution.
