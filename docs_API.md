# REST API Specification (v1)

Base path: `/api/v1`

## Product APIs
- `GET /cards/search`
- `GET /cards/{card_id}`
- `GET /cards/{card_id}/comps`
- `GET /cards/{card_id}/stats`
- `GET /cards/{card_id}/sales-history`
- `GET /cards/{card_id}/comparison/raw-vs-psa10`
- `GET /valuations/cards/{card_id}`
- `GET/POST /collection/items`
- `GET/PUT/DELETE /collection/items/{item_id}`
- `GET /dashboard/summary`
- `GET /dashboard/recent-additions`
- `GET /dashboard/distribution`

## Internal ingestion APIs
- `POST /internal/ingestion/run?mode=daily|hourly&tracked_card_ids=1,2`
- `GET /internal/ingestion/runs`
- `GET /internal/ingestion/unmatched`
- `GET /internal/ingestion/low-confidence`
- `GET /internal/ingestion/parse-errors`
- `GET /internal/ingestion/source-health`

## Ingestion flow contract
`adapter fetch -> raw_market_listing -> normalized_sale -> listing_card_match -> confidence gate -> sale_comp`

## Ingestion guardrail contract
- Idempotent upsert at raw and normalized layers.
- Preserve raw payload/source listing ids for traceability.
- Promote to comps only when confidence threshold is met.
- Persist parse/unmatched/low-confidence issues for review.
- Support `daily` and `hourly tracked-card` refresh modes.
