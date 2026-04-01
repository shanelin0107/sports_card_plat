INSERT INTO sport (id, name) VALUES (1, 'Baseball'), (2, 'Basketball') ON CONFLICT DO NOTHING;
INSERT INTO brand (id, name) VALUES (1, 'Topps'), (2, 'Panini') ON CONFLICT DO NOTHING;
INSERT INTO grade_company (id, name) VALUES (1, 'PSA') ON CONFLICT DO NOTHING;
INSERT INTO source_platform (id, name, source_type) VALUES (1, 'eBay', 'marketplace') ON CONFLICT DO NOTHING;
INSERT INTO owner_profile (id, display_name) VALUES (1, 'Personal Collection') ON CONFLICT DO NOTHING;

INSERT INTO card_set (id, brand_id, sport_id, name, release_year)
VALUES
  (1, 1, 1, 'Topps Chrome', 2023),
  (2, 2, 2, 'Panini Prizm', 2023)
ON CONFLICT DO NOTHING;

INSERT INTO player (id, sport_id, full_name)
VALUES
  (1, 1, 'Shohei Ohtani'),
  (2, 2, 'Victor Wembanyama')
ON CONFLICT DO NOTHING;

INSERT INTO card (id, sport_id, year, brand_id, set_id, player_id, card_number, title, slug, search_text_normalized, default_image_url, rookie_flag, autograph_flag, patch_flag)
VALUES
  (1, 1, 2023, 1, 1, 1, '1', '2023 Topps Chrome Shohei Ohtani #1', '2023-topps-chrome-shohei-ohtani-1', '2023 topps chrome shohei ohtani 1 psa 10 raw', 'https://example.com/ohtani.jpg', false, false, false),
  (2, 2, 2023, 2, 2, 2, '136', '2023 Panini Prizm Victor Wembanyama #136 RC', '2023-panini-prizm-victor-wembanyama-136', '2023 panini prizm victor wembanyama 136 rc psa 10 raw silver', 'https://example.com/wemby.jpg', true, false, false)
ON CONFLICT DO NOTHING;

INSERT INTO card_parallel (id, card_id, parallel_name, variation_name, is_short_print)
VALUES
  (1, 1, 'Base', 'Base', false),
  (2, 2, 'Silver', 'Base', false)
ON CONFLICT DO NOTHING;

INSERT INTO card_grade_profile (id, card_id, card_parallel_id, grade_company_id, grade_value, label, is_raw)
VALUES
  (1, 1, 1, null, null, 'Raw', true),
  (2, 1, 1, 1, '10', 'PSA 10', false),
  (3, 2, 2, null, null, 'Raw', true),
  (4, 2, 2, 1, '10', 'PSA 10', false)
ON CONFLICT DO NOTHING;

INSERT INTO raw_market_listing (id, source_platform_id, source_listing_id, sold_at_raw, listing_title_raw, listing_url_raw, condition_raw, price_raw, shipping_raw, payload_json)
VALUES
  (1, 1, 'EBAY-SHO-001', '2026-03-20', 'Shohei Ohtani 2023 Topps Chrome PSA 10', 'https://example.com/1', 'PSA 10', '$180.00', '$5.00', '{"seed": true}'),
  (2, 1, 'EBAY-SHO-002', '2026-03-10', 'Topps Chrome Ohtani PSA 10', 'https://example.com/2', 'PSA 10', '$175.00', '$5.00', '{"seed": true}'),
  (3, 1, 'EBAY-SHO-RAW-001', '2026-03-01', 'Topps Chrome Ohtani Raw', 'https://example.com/5', 'Raw', '$95.00', '$5.00', '{"seed": true}'),
  (4, 1, 'EBAY-VIC-001', '2026-03-22', 'Wembanyama Prizm Silver PSA 10', 'https://example.com/3', 'PSA 10', '$420.00', '$10.00', '{"seed": true}'),
  (5, 1, 'EBAY-VIC-002', '2026-03-05', 'Wembanyama Prizm Silver PSA 9', 'https://example.com/4', 'PSA 9', '$260.00', '$8.00', '{"seed": true}')
ON CONFLICT DO NOTHING;

INSERT INTO normalized_sale (id, raw_market_listing_id, source_platform_id, source_listing_id, sold_at, sale_price, shipping_price, total_price, currency, grade_company_id, grade_value, parsed_year, parsed_brand, parsed_set, parsed_player, parsed_card_number, parsed_parallel, parsed_variation)
VALUES
  (1, 1, 1, 'EBAY-SHO-001', NOW() - INTERVAL '5 days', 180.00, 5.00, 185.00, 'USD', 1, '10', 2023, 'Topps', 'Topps Chrome', 'Shohei Ohtani', '1', 'Base', 'Base'),
  (2, 2, 1, 'EBAY-SHO-002', NOW() - INTERVAL '15 days', 175.00, 5.00, 180.00, 'USD', 1, '10', 2023, 'Topps', 'Topps Chrome', 'Shohei Ohtani', '1', 'Base', 'Base'),
  (3, 3, 1, 'EBAY-SHO-RAW-001', NOW() - INTERVAL '30 days', 95.00, 5.00, 100.00, 'USD', null, null, 2023, 'Topps', 'Topps Chrome', 'Shohei Ohtani', '1', 'Base', 'Base'),
  (4, 4, 1, 'EBAY-VIC-001', NOW() - INTERVAL '3 days', 420.00, 10.00, 430.00, 'USD', 1, '10', 2023, 'Panini', 'Panini Prizm', 'Victor Wembanyama', '136', 'Silver', 'Base'),
  (5, 5, 1, 'EBAY-VIC-002', NOW() - INTERVAL '21 days', 260.00, 8.00, 268.00, 'USD', 1, '9', 2023, 'Panini', 'Panini Prizm', 'Victor Wembanyama', '136', 'Silver', 'Base')
ON CONFLICT DO NOTHING;

INSERT INTO listing_card_match (id, normalized_sale_id, card_id, card_parallel_id, match_method, confidence_score, is_primary, reason_codes)
VALUES
  (1, 1, 1, 1, 'rule_based', 0.98, true, '["PLAYER_MATCH", "CARD_NUMBER_MATCH"]'),
  (2, 2, 1, 1, 'rule_based', 0.97, true, '["PLAYER_MATCH", "CARD_NUMBER_MATCH"]'),
  (3, 3, 1, 1, 'rule_based', 0.95, true, '["RAW_CONDITION_MATCH"]'),
  (4, 4, 2, 2, 'rule_based', 0.99, true, '["PLAYER_MATCH", "CARD_NUMBER_MATCH"]'),
  (5, 5, 2, 2, 'rule_based', 0.96, true, '["PLAYER_MATCH", "CARD_NUMBER_MATCH"]')
ON CONFLICT DO NOTHING;

INSERT INTO sale_comp (id, normalized_sale_id, card_id, card_parallel_id, grade_company_id, grade_value, sold_at, sale_price, shipping_price, total_price, currency)
VALUES
  (1, 1, 1, 1, 1, '10', NOW() - INTERVAL '5 days', 180.00, 5.00, 185.00, 'USD'),
  (2, 2, 1, 1, 1, '10', NOW() - INTERVAL '15 days', 175.00, 5.00, 180.00, 'USD'),
  (3, 3, 1, 1, null, null, NOW() - INTERVAL '30 days', 95.00, 5.00, 100.00, 'USD'),
  (4, 4, 2, 2, 1, '10', NOW() - INTERVAL '3 days', 420.00, 10.00, 430.00, 'USD'),
  (5, 5, 2, 2, 1, '9', NOW() - INTERVAL '21 days', 260.00, 8.00, 268.00, 'USD')
ON CONFLICT DO NOTHING;

INSERT INTO collection_item (owner_profile_id, card_id, card_parallel_id, grade_company_id, grade_value, is_graded, quantity, purchase_price, purchase_date, condition, notes)
VALUES
  (1, 1, 1, 1, '10', true, 1, 150.00, '2025-11-10', 'PSA 10', 'Bought as long-term hold'),
  (1, 2, 2, 1, '10', true, 1, 390.00, '2026-01-20', 'PSA 10', 'High liquidity rookie')
ON CONFLICT DO NOTHING;
