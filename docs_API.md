# REST API Specification (v1)

Base path: `/api/v1`. When `API_KEY` is set on the backend, every request needs `X-API-Key: <key>`
(the Next.js server adds it; browsers call `/api/backend/*` on the frontend instead).

Grade parameters accept `raw`, `psa10`, `psa9`, … or `all`. Windows: `30d`, `90d`, `1y`, `all`.

## Product APIs
- `GET /cards/search?q=&year=&brand=&player=&limit=` — every word in `q` must match (AND)
- `GET /cards/{card_id}?grade=&window=` — metadata, valuation for one grade (defaults to the most-traded grade), stats, raw-vs-PSA10, available grades
- `GET /cards/{card_id}/comps?grade=&window=&limit=`
- `GET /cards/{card_id}/stats?grade=&window=`
- `GET /cards/{card_id}/sales-history?grade=&window=&bucket=day|week|month`
- `GET /cards/{card_id}/comparison/raw-vs-psa10`
- `GET /valuations/cards/{card_id}?grade=&window=`
- `GET/POST /collection/items` — items include card identity, grade label, valuation, P&L, sparkline
- `GET/PUT/DELETE /collection/items/{item_id}`
- `GET /dashboard/summary` — totals, daily change, gainers/losers (records a daily valuation snapshot)
- `GET /dashboard/recent-additions`
- `GET /dashboard/recent-comps?limit=&held_only=`
- `GET /dashboard/distribution?by=brand|player|grade|set|year`
- `GET /catalog/grade-companies`
- `GET /catalog/cards/{card_id}/parallels`
- `POST /catalog/cards` — add a card (player/brand/set created as needed)

## Internal ingestion APIs
- `POST /internal/ingestion/run?mode=daily|hourly&tracked_card_ids=1,2`
- `GET /internal/ingestion/runs`
- `GET /internal/ingestion/issues?status=open|resolved|dismissed|all&issue_type=`
- `POST /internal/ingestion/issues/{id}/resolve` `{ "card_id": 3 }` — manual match, promotes the sale to a comp
- `POST /internal/ingestion/issues/{id}/dismiss`
- `GET /internal/ingestion/unmatched` · `/low-confidence` · `/parse-errors` (open issues, kept for compatibility)
- `GET /internal/ingestion/source-health` — per-source 7-day stats, open issue counts, last run

## Ingestion flow contract
`adapter fetch -> raw_market_listing -> normalized_sale -> listing_card_match -> confidence gate -> sale_comp`

## Ingestion guardrail contract
- Idempotent upsert at raw, normalized, match and comp layers; re-running a feed creates no duplicates.
- Preserve raw payload/source listing ids for traceability.
- Promote to comps only when confidence ≥ 0.75; a sale is never matched to a different player.
- Persist parse/unmatched/low-confidence issues once per listing; resolved/dismissed issues are not re-opened.
- A failed run is rolled back and marked `failed` with its error message.
- Support `daily` and `hourly tracked-card` refresh modes.

## Valuation rules
1. Exact comps: same card **and same grade** (PSA 10 is never priced off PSA 9 or raw) and parallel.
2. Fewer than 3 in the window → widen to 1y, then all-time, with lower confidence (`WIDENED_TO_*`).
3. Still thin → blend in same player/brand/year/grade comps from other cards (`SIMILAR_CARDS_BLENDED`).
4. Estimate = median; range = interquartile range (min/max under 4 comps).
