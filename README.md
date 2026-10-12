# Slab Terminal — Sports Card Portfolio (v0.2)

A seed-first sports-card intelligence MVP with deterministic valuation and a **low-risk ingestion layer** designed for lawful public marketplace workflows.

## Project overview
- Single-user MVP for sports cards.
- Topps/Panini-first scope.
- Raw + PSA-first valuation and comparison.
- Deterministic, auditable pipelines and valuation logic.

## Lawful ingestion phase: safest approach (phase 1)
1. Prefer official marketplace APIs and lawful export paths.
2. If API access is unavailable, use manual/public export data ingestion files (no aggressive crawler behavior in app code).
3. Keep adapter pluggable so source-specific logic is isolated.
4. Preserve raw payloads unchanged for traceability and debugging.

### API vs parsing boundary
- **API/pre-export path (preferred):** adapter ingests structured sold/completed listing exports.
- **Public page parsing path (deferred/manual):** only considered where legally permissible and with strict rate limits + review.

### Guardrails implemented
- Idempotent upserts keyed by `(source_platform_id, source_listing_id)`.
- Promotion gate: only high-confidence matches move into `sale_comp`.
- Run tracking, issue tracking, and source health visibility.
- Configurable modes: `daily` and `hourly tracked-card`.

## Architecture summary
`source adapter -> raw_market_listing -> normalized_sale -> listing_card_match -> sale_comp -> valuation/dashboard`

## Local setup
```bash
cp .env.example .env
docker compose up --build
```

App URLs:
- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

The backend creates/upgrades the schema and loads demo data on startup, so a fresh database
needs no manual SQL. Existing databases from v0.1 are upgraded in place.

### Without Docker
```bash
# API (needs a Postgres you can reach)
cd backend && pip install -r requirements.txt
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/sports_cards uvicorn app.main:app --reload

# Web
cd frontend && npm install
API_BASE_URL=http://localhost:8000 npm run dev
```

### Tests
```bash
cd backend && pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/sports_cards_test pytest
```
CI (`.github/workflows/ci.yml`) runs the backend tests against Postgres and type-checks and builds the frontend.

## Deploying
See [DEPLOY.md](DEPLOY.md) — Neon (Postgres) + Render (API) + Vercel (web), all on free tiers,
with a site password and an API key between the web app and the API.

## Reseed deterministically
```bash
./scripts/reseed_db.sh
```

## Ingestion run commands (internal APIs)
```bash
# Run daily ingest from eBay-oriented lawful feed stub
curl -X POST "http://localhost:8000/api/v1/internal/ingestion/run?mode=daily"

# Run hourly tracked-card refresh (example card ids)
curl -X POST "http://localhost:8000/api/v1/internal/ingestion/run?mode=hourly&tracked_card_ids=1,2"

# Visibility endpoints
curl "http://localhost:8000/api/v1/internal/ingestion/runs"
curl "http://localhost:8000/api/v1/internal/ingestion/unmatched"
curl "http://localhost:8000/api/v1/internal/ingestion/low-confidence"
curl "http://localhost:8000/api/v1/internal/ingestion/parse-errors"
curl "http://localhost:8000/api/v1/internal/ingestion/source-health"
```

## Seed + demo data notes
- `seed/demo_seed.sql` seeds baseline cards/comps/collection.
- `seed/ebay_sample_feed.json` simulates lawful sold/completed feed input for ingestion service testing.

## Manual review before trusting production-like data
1. Inspect unmatched listings and low-confidence matches.
2. Confirm parse-error trends are low and explainable.
3. Spot-check promoted comps against raw payload/source listing ids.
4. Validate card match confidence thresholds and reason codes.

## Known limitations / TODO
- eBay adapter currently uses lawful feed stub (fixture-based), not live API wiring.
- Backoff/retry are scaffold-level; real source API policies must be implemented per contract.
- No auth/alerts yet.
- No LLM-based valuation.

## Next roadmap
1. Wire official source API client where permitted.
2. Add stronger parser patterns and confidence calibration.
3. Add manual-review queue UX for ambiguous matches.
4. Add snapshot-driven trend analytics.

## What changed in v0.2
**Bug fixes**
- Valuation now prices each holding at its own grade (PSA 10 was being averaged with PSA 9 / raw sales).
- Stale comps no longer zero out the portfolio: the window widens 90d → 1y → all with lower confidence.
- Seed data advanced the ID sequences, so the first ingestion no longer crashes with a duplicate key.
- Ingestion: reads real sold dates, parses all grades (PSA 9, BGS 9.5…), fixed `#136` being read as `#1`,
  matches against the catalog instead of hard-coded player names, rolls back failed runs,
  and finds its feed file inside Docker.
- Multi-word search (`2023 topps ohtani psa 10`) now works; `%`/`_` are escaped.
- In Docker, server-rendered pages now reach the API (`API_BASE_URL=http://backend:8000`).
- Next.js 15.4.6 / React 19.1.1 → 15.5.27 / 19.1.9 (patches the Dec 2025 React Server Components advisories).

**New**
- Terminal-style UI: dashboard, collection manager, card detail with grade/window tabs, ingestion review queue.
- Add your own cards to the catalog; manual match / dismiss for ingestion issues.
- Daily change and gainers/losers via daily valuation snapshots.
- Site password + API key for public deployment; Render/Vercel config; CI; 14 backend tests.
