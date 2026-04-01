# Sports Card Intelligence Platform MVP (Phase 1) - Concise PRD

## 1) Objective
Build a **single-user**, personal-use MVP that provides search, comp history, valuation baseline, and collection tracking for sports cards (Topps/Panini focus), with a foundation that can later support ingestion adapters and richer analytics.

## 2) In Scope (Phase 1)
- Card catalog with canonical card identity.
- Sold comp storage and querying (seed/demo data only).
- Collection tracking with purchase and condition metadata.
- Deterministic valuation baseline from comp windows.
- REST API for search, comps, valuation, collection, and dashboard metrics.
- Basic dashboard UI (functional, not polished).
- Local dev via Docker Compose.

## 3) Out of Scope (Phase 1)
- Live scraping/ingestion adapters (eBay integration deferred).
- Auth, multi-user tenancy, alerts, notifications.
- Highly polished UI, advanced charting, mobile optimizations.
- ML/LLM-powered valuation logic.

## 4) Primary Users & Jobs
Single owner/user wants to:
1. Search cards with fuzzy text (e.g., "2023 topps ohtani psa 10").
2. Review recent comps and sales history.
3. View estimated fair value with transparent deterministic logic.
4. Track personal holdings and unrealized P&L.
5. View collection-level summary metrics.

## 5) Functional Requirements
- Fuzzy search over year/brand/set/player/card number/parallel/grade.
- Filtering by year, brand, player, set, grade, sport.
- Card detail endpoint with recent 10 comps and price stats (avg/median/windowed).
- Collection CRUD and dashboard summary.
- Valuation endpoint with explanation payload (rule + comp window used).

## 6) Non-Functional Requirements
- Maintainable and modular architecture.
- Strong schema normalization for extensibility.
- Deterministic valuation behavior.
- Reproducible local startup (`docker compose up`).
- Seed data for realistic local testing.

## 7) Assumptions
- Single-user means `owner_profile` can be one row for now.
- Primary grade company is PSA in phase 1, but schema supports more.
- Comp source metadata will include placeholder source records to support future ingestion.
- Search quality can be improved later with Postgres full-text + trigram indexing.

## 8) Success Criteria (Phase 1)
- Developer can run stack locally and query seeded cards/comps/collection.
- Search + filters work for canonical identity fields.
- Collection summary returns estimated value and unrealized P&L.
- API contracts stable enough for iterative frontend development.
