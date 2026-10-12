# Phased Implementation Plan

## Phase 1A (done)
- Canonical schema and deterministic valuation foundation.
- Seed-first product flows for search/detail/collection/dashboard.

## Phase 1B (done)
- Introduce lawful ingestion application layer:
  - source adapter interface
  - eBay-oriented lawful feed stub path
  - ingestion run tracking + issue tracking
  - normalization/matching/promotion pipeline
  - internal visibility endpoints

## Phase 1C (done — v0.2)
- Grade-aware, batched valuation with window fallback; daily snapshots for day-over-day change.
- Manual review UX for unmatched/low-confidence listings (resolve / dismiss).
- Owner-managed catalog (add cards), Terminal UI, site password + API key, hosted deploy config.

## Phase 2
- Replace feed stub with officially permitted source API integration.
- Add robust retry/backoff/circuit behavior per source policy.

## Phase 3
- Calibrate match confidence and low-liquidity valuation quality.
- Expand source adapters beyond first marketplace.
