# Normalized PostgreSQL Schema

## Canonical Identity Layer
- `sport(id, name)`
- `brand(id, name)`
- `card_set(id, brand_id, sport_id, name, release_year)`
- `player(id, sport_id, full_name)`
- `grade_company(id, name)`
- `card(id, sport_id, year, brand_id, set_id, player_id, card_number, title, slug, search_text_normalized, default_image_url, rookie_flag, autograph_flag, patch_flag)`
- `card_parallel(id, card_id, parallel_name, variation_name, is_short_print, print_run)`
- `card_grade_profile(id, card_id, card_parallel_id, grade_company_id, grade_value, label, is_raw)`

### Canonical identity strategy
- `card` stores the base identity (year/brand/set/player/card_number).
- `card_parallel` isolates parallel + variation identity from base card.
- `card_grade_profile` defines valid grade variants and explicitly supports raw (`is_raw = true`, grade fields nullable).

## Ingestion + Normalization Layer
- `source_platform(id, name, source_type)`
- `raw_market_listing(id, source_platform_id, source_listing_id, fetched_at, sold_at_raw, listing_title_raw, listing_url_raw, condition_raw, price_raw, shipping_raw, payload_json)`
- `normalized_sale(id, raw_market_listing_id, source_platform_id, source_listing_id, sold_at, sale_price, shipping_price, total_price, currency, grade_company_id, grade_value, parsed_year, parsed_brand, parsed_set, parsed_player, parsed_card_number, parsed_parallel, parsed_variation, normalized_notes)`
- `listing_card_match(id, normalized_sale_id, card_id, card_parallel_id, match_method, confidence_score, is_primary, reason_codes)`

### Why this layer exists
- Preserve immutable raw source payloads (`raw_market_listing`).
- Store deterministic parsed/normalized fields (`normalized_sale`).
- Separate matching confidence and rationale from normalized parsing (`listing_card_match`).

## Comp/Valuation Layer
- `sale_comp(id, normalized_sale_id, card_id, card_parallel_id, grade_company_id, grade_value, sold_at, sale_price, shipping_price, total_price, currency)`
- `valuation_snapshot(id, card_id, card_parallel_id, grade_company_id, grade_value, as_of_date, window_days, estimated_price, low_estimate, high_estimate, confidence_score, exact_comp_count, similar_comp_count, methodology, reason_codes, explanation_json)`

## Collection + Analytics Layer
- `owner_profile(id, display_name)`
- `collection_item(id, owner_profile_id, card_id, card_parallel_id, grade_company_id, grade_value, is_graded, quantity, purchase_price, purchase_date, condition, notes, image_url, uploaded_image_path)`
- `saved_search(id, query_text, filters_json, last_run_at, run_count)`

## Suggested Indexes
- `card(slug)` unique.
- `card(search_text_normalized)` with trigram/FTS index.
- `raw_market_listing(source_platform_id, source_listing_id)` unique.
- `normalized_sale(raw_market_listing_id)` unique.
- `listing_card_match(normalized_sale_id, confidence_score desc)`.
- `sale_comp(card_id, sold_at desc)`.
- `valuation_snapshot(card_id, as_of_date desc)`.


## Ingestion Operations Tables
- `ingestion_run(id, source_platform_id, mode, status, started_at, completed_at, fetched_count, raw_upserted_count, normalized_count, matched_count, promoted_count, low_confidence_count, parse_error_count, error_message)`
- `ingestion_issue(id, ingestion_run_id, issue_type, source_listing_id, normalized_sale_id, details_json, created_at)`
