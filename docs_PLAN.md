# Phased Implementation Plan

## Phase 1A (done)
- Canonical schema and deterministic valuation foundation.
- Seed-first product flows for search/detail/collection/dashboard.

## Phase 1B (current)
- Introduce lawful ingestion application layer:
  - source adapter interface
  - eBay-oriented lawful feed stub path
  - ingestion run tracking + issue tracking
  - normalization/matching/promotion pipeline
  - internal visibility endpoints

## Phase 2
- Replace feed stub with officially permitted source API integration.
- Add robust retry/backoff/circuit behavior per source policy.
- Add manual review UX for unmatched/low-confidence listings.

## Phase 3
- Calibrate match confidence and low-liquidity valuation quality.
- Expand source adapters beyond first marketplace.
