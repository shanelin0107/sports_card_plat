# Text-Based System Architecture

```text
+-----------------------------+
| Next.js Web UI              |
| - Search / detail / collect |
| - Dashboard / review        |
+-------------+---------------+
              |
              | REST
              v
+-----------------------------+
| FastAPI Backend             |
|                             |
| Product APIs                |
| - cards / valuations        |
| - collection / dashboard    |
|                             |
| Internal Ingestion APIs     |
| - run ingestion jobs        |
| - run history/health        |
| - unmatched/low confidence  |
| - parse error visibility    |
|                             |
| Ingestion Services          |
| - Source adapter interface  |
| - eBay public adapter path  |
| - Normalization pipeline    |
| - Matching + promotion      |
+-------------+---------------+
              |
              | SQL
              v
+-----------------------------+
| PostgreSQL                  |
| - raw_market_listing        |
| - normalized_sale           |
| - listing_card_match        |
| - sale_comp                 |
| - ingestion_run/issues      |
| - valuation_snapshot        |
+-----------------------------+
```

## Lawful MVP ingestion path
`adapter fetch -> raw_market_listing -> normalized_sale -> listing_card_match -> (confidence gate) -> sale_comp`

## Compliance and safety guardrails
- Prefer official APIs / lawful manual export workflows first.
- No aggressive scraping in this phase.
- Add conservative refresh schedules (`daily`, `hourly tracked`).
- Apply retry/backoff in adapter integrations when direct calls are introduced.
- Preserve source traceability (`source_listing_id`, raw payload).
- Idempotent upserts on raw and normalized records.
- Promote to `sale_comp` only for accepted/high-confidence matches.
- Surface parse errors/unmatched/low-confidence for manual review.
