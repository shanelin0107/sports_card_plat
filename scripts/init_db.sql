CREATE TABLE IF NOT EXISTS sport (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS brand (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS card_set (
  id SERIAL PRIMARY KEY,
  brand_id INT NOT NULL REFERENCES brand(id),
  sport_id INT NOT NULL REFERENCES sport(id),
  name VARCHAR(150) NOT NULL,
  release_year INT NOT NULL
);

CREATE TABLE IF NOT EXISTS player (
  id SERIAL PRIMARY KEY,
  sport_id INT NOT NULL REFERENCES sport(id),
  full_name VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS grade_company (
  id SERIAL PRIMARY KEY,
  name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS source_platform (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) UNIQUE NOT NULL,
  source_type VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS card (
  id SERIAL PRIMARY KEY,
  sport_id INT NOT NULL REFERENCES sport(id),
  year INT NOT NULL,
  brand_id INT NOT NULL REFERENCES brand(id),
  set_id INT NOT NULL REFERENCES card_set(id),
  player_id INT NOT NULL REFERENCES player(id),
  card_number VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  slug VARCHAR(255) NOT NULL UNIQUE,
  search_text_normalized TEXT NOT NULL,
  default_image_url TEXT,
  rookie_flag BOOLEAN DEFAULT FALSE,
  autograph_flag BOOLEAN DEFAULT FALSE,
  patch_flag BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS card_parallel (
  id SERIAL PRIMARY KEY,
  card_id INT NOT NULL REFERENCES card(id),
  parallel_name VARCHAR(100) NOT NULL,
  variation_name VARCHAR(100) DEFAULT 'Base',
  is_short_print BOOLEAN DEFAULT FALSE,
  print_run INT,
  UNIQUE (card_id, parallel_name, variation_name)
);

CREATE TABLE IF NOT EXISTS card_grade_profile (
  id SERIAL PRIMARY KEY,
  card_id INT NOT NULL REFERENCES card(id),
  card_parallel_id INT REFERENCES card_parallel(id),
  grade_company_id INT REFERENCES grade_company(id),
  grade_value VARCHAR(20),
  label VARCHAR(120) NOT NULL,
  is_raw BOOLEAN DEFAULT FALSE,
  UNIQUE (card_id, card_parallel_id, grade_company_id, grade_value)
);

CREATE TABLE IF NOT EXISTS raw_market_listing (
  id SERIAL PRIMARY KEY,
  source_platform_id INT NOT NULL REFERENCES source_platform(id),
  source_listing_id VARCHAR(120) NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sold_at_raw VARCHAR(100),
  listing_title_raw TEXT NOT NULL,
  listing_url_raw TEXT,
  condition_raw VARCHAR(120),
  price_raw VARCHAR(120),
  shipping_raw VARCHAR(120),
  payload_json JSONB NOT NULL,
  UNIQUE (source_platform_id, source_listing_id)
);

CREATE TABLE IF NOT EXISTS normalized_sale (
  id SERIAL PRIMARY KEY,
  raw_market_listing_id INT NOT NULL UNIQUE REFERENCES raw_market_listing(id),
  source_platform_id INT NOT NULL REFERENCES source_platform(id),
  source_listing_id VARCHAR(120) NOT NULL,
  sold_at TIMESTAMPTZ NOT NULL,
  sale_price NUMERIC(12,2) NOT NULL,
  shipping_price NUMERIC(12,2) NOT NULL DEFAULT 0,
  total_price NUMERIC(12,2) NOT NULL,
  currency VARCHAR(3) NOT NULL DEFAULT 'USD',
  grade_company_id INT REFERENCES grade_company(id),
  grade_value VARCHAR(20),
  parsed_year INT,
  parsed_brand VARCHAR(100),
  parsed_set VARCHAR(150),
  parsed_player VARCHAR(150),
  parsed_card_number VARCHAR(50),
  parsed_parallel VARCHAR(100),
  parsed_variation VARCHAR(100),
  normalized_notes TEXT
);

CREATE TABLE IF NOT EXISTS listing_card_match (
  id SERIAL PRIMARY KEY,
  normalized_sale_id INT NOT NULL REFERENCES normalized_sale(id),
  card_id INT NOT NULL REFERENCES card(id),
  card_parallel_id INT REFERENCES card_parallel(id),
  match_method VARCHAR(50) NOT NULL,
  confidence_score NUMERIC(5,4) NOT NULL,
  is_primary BOOLEAN DEFAULT TRUE,
  reason_codes JSONB
);

CREATE TABLE IF NOT EXISTS sale_comp (
  id SERIAL PRIMARY KEY,
  normalized_sale_id INT NOT NULL UNIQUE REFERENCES normalized_sale(id),
  card_id INT NOT NULL REFERENCES card(id),
  card_parallel_id INT REFERENCES card_parallel(id),
  grade_company_id INT REFERENCES grade_company(id),
  grade_value VARCHAR(20),
  sold_at TIMESTAMPTZ NOT NULL,
  sale_price NUMERIC(12,2) NOT NULL,
  shipping_price NUMERIC(12,2) NOT NULL DEFAULT 0,
  total_price NUMERIC(12,2) NOT NULL,
  currency VARCHAR(3) NOT NULL DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS owner_profile (
  id SERIAL PRIMARY KEY,
  display_name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_item (
  id SERIAL PRIMARY KEY,
  owner_profile_id INT NOT NULL REFERENCES owner_profile(id),
  card_id INT NOT NULL REFERENCES card(id),
  card_parallel_id INT REFERENCES card_parallel(id),
  grade_company_id INT REFERENCES grade_company(id),
  grade_value VARCHAR(20),
  is_graded BOOLEAN DEFAULT FALSE,
  quantity INT NOT NULL DEFAULT 1,
  purchase_price NUMERIC(12,2) NOT NULL,
  purchase_date DATE NOT NULL,
  condition VARCHAR(100),
  notes TEXT,
  image_url TEXT,
  uploaded_image_path TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS saved_search (
  id SERIAL PRIMARY KEY,
  query_text VARCHAR(255) NOT NULL,
  filters_json JSONB,
  last_run_at TIMESTAMPTZ,
  run_count INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS valuation_snapshot (
  id SERIAL PRIMARY KEY,
  card_id INT NOT NULL REFERENCES card(id),
  card_parallel_id INT REFERENCES card_parallel(id),
  grade_company_id INT REFERENCES grade_company(id),
  grade_value VARCHAR(20),
  as_of_date DATE NOT NULL,
  window_days INT NOT NULL,
  estimated_price NUMERIC(12,2) NOT NULL,
  low_estimate NUMERIC(12,2),
  high_estimate NUMERIC(12,2),
  confidence_score NUMERIC(5,4) NOT NULL DEFAULT 0,
  exact_comp_count INT NOT NULL DEFAULT 0,
  similar_comp_count INT NOT NULL DEFAULT 0,
  methodology VARCHAR(100) NOT NULL,
  reason_codes JSONB,
  explanation_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_card_search_text ON card(search_text_normalized);
CREATE INDEX IF NOT EXISTS idx_sale_comp_card_sold_at ON sale_comp(card_id, sold_at DESC);


CREATE TABLE IF NOT EXISTS ingestion_run (
  id SERIAL PRIMARY KEY,
  source_platform_id INT NOT NULL REFERENCES source_platform(id),
  mode VARCHAR(30) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'running',
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  fetched_count INT NOT NULL DEFAULT 0,
  raw_upserted_count INT NOT NULL DEFAULT 0,
  normalized_count INT NOT NULL DEFAULT 0,
  matched_count INT NOT NULL DEFAULT 0,
  promoted_count INT NOT NULL DEFAULT 0,
  low_confidence_count INT NOT NULL DEFAULT 0,
  parse_error_count INT NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_issue (
  id SERIAL PRIMARY KEY,
  ingestion_run_id INT NOT NULL REFERENCES ingestion_run(id),
  issue_type VARCHAR(40) NOT NULL,
  source_listing_id VARCHAR(120),
  normalized_sale_id INT REFERENCES normalized_sale(id),
  details_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- v0.2 additive migrations (safe to re-run on an existing database)
-- ---------------------------------------------------------------------------

-- Review queue state for ingestion issues (open -> resolved | dismissed)
ALTER TABLE ingestion_issue ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'open';
ALTER TABLE ingestion_issue ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE ingestion_issue ADD COLUMN IF NOT EXISTS resolution_card_id INT REFERENCES card(id);
CREATE INDEX IF NOT EXISTS idx_ingestion_issue_status ON ingestion_issue(status, issue_type);

-- One snapshot per holding grade per day, used for daily change / gainers & losers
CREATE UNIQUE INDEX IF NOT EXISTS uq_valuation_snapshot_day
  ON valuation_snapshot (card_id, COALESCE(grade_company_id, 0), COALESCE(grade_value, ''), as_of_date, window_days);

CREATE INDEX IF NOT EXISTS idx_sale_comp_card_grade ON sale_comp(card_id, grade_value, sold_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_item_owner ON collection_item(owner_profile_id);

-- Seed rows are inserted with explicit ids, which leaves SERIAL sequences at 1 and
-- makes the next INSERT collide with an existing primary key. Re-align every
-- sequence with its table's max(id).
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT c.relname AS tbl, s.relname AS seq
    FROM pg_class s
    JOIN pg_depend d ON d.objid = s.oid AND d.deptype = 'a'
    JOIN pg_class c ON c.oid = d.refobjid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE s.relkind = 'S' AND n.nspname = current_schema()
  LOOP
    EXECUTE format('SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I), 0) + 1, false)', r.seq, r.tbl);
  END LOOP;
END $$;

-- v0.3: owner photos for holdings (stored in Postgres so they survive redeploys on
-- hosts with ephemeral disks, e.g. Render).
CREATE TABLE IF NOT EXISTS collection_item_photo (
  collection_item_id INT PRIMARY KEY REFERENCES collection_item(id) ON DELETE CASCADE,
  content_type VARCHAR(50) NOT NULL,
  data BYTEA NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The original seed used placeholder URLs that never resolved; clear them so the UI
-- shows its own placeholder instead of a broken image.
UPDATE card SET default_image_url = NULL WHERE default_image_url LIKE 'https://example.com/%';

-- v0.4: AI price research jobs (Claude + web search). Results are suggestions only;
-- nothing becomes a comp until the owner confirms it.
CREATE TABLE IF NOT EXISTS ai_price_research (
  id SERIAL PRIMARY KEY,
  card_id INT REFERENCES card(id) ON DELETE SET NULL,
  query TEXT NOT NULL,
  grade VARCHAR(20),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  model VARCHAR(80),
  result_json JSONB,
  error_message TEXT,
  searches_used INT NOT NULL DEFAULT 0,
  input_tokens INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ai_price_research_card ON ai_price_research(card_id, created_at DESC);
