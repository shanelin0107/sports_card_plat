export type Holding = {
  id: number;
  card_id: number;
  card_parallel_id: number | null;
  grade_company_id: number | null;
  grade_value: string | null;
  is_graded: boolean;
  quantity: number;
  purchase_price: number;
  purchase_date: string;
  condition: string | null;
  notes: string | null;
  title: string | null;
  player: string | null;
  year: number | null;
  brand: string | null;
  card_set: string | null;
  card_number: string | null;
  parallel: string | null;
  rookie_flag: boolean;
  grade_label: string;
  estimated_value: number | null;
  estimated_unit_price: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  confidence_score: number | null;
  valuation_method: string | null;
  exact_comp_count: number;
  spark: number[];
};

export type Mover = {
  collection_item_id: number;
  card_id: number;
  title: string;
  grade_label: string;
  change: number;
  change_pct: number | null;
};

export type Summary = {
  total_items: number;
  positions: number;
  graded_positions: number;
  unpriced_positions: number;
  cost_basis: number;
  estimated_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number | null;
  daily_change: number | null;
  daily_change_pct: number | null;
  gainers: Mover[];
  losers: Mover[];
  as_of: string;
};

export type RecentComp = {
  id: number;
  card_id: number;
  title: string;
  player: string;
  grade_label: string;
  sold_at: string;
  total_price: number;
};

export type IngestionRun = {
  id: number;
  mode: string;
  status: 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  fetched_count: number;
  normalized_count: number;
  matched_count: number;
  promoted_count: number;
  low_confidence_count: number;
  parse_error_count: number;
  error_message: string | null;
};

export type SourceHealth = {
  sources: {
    source: string;
    runs_last_7d: number;
    parse_errors_last_7d: number;
    promoted_last_7d: number;
    failed_runs_last_7d: number;
    last_run_at: string | null;
    healthy: boolean;
  }[];
  open_issues: { unmatched: number; low_confidence: number; parse_error: number };
  last_run: IngestionRun | null;
};

export type IngestionIssue = {
  id: number;
  issue_type: 'unmatched' | 'low_confidence' | 'parse_error';
  status: 'open' | 'resolved' | 'dismissed';
  source_listing_id: string | null;
  normalized_sale_id: number | null;
  details: {
    title?: string;
    price?: number;
    sold_at?: string;
    grade?: string;
    url?: string;
    confidence?: number;
    reason?: string;
    suggested_card_id?: number;
  } | null;
  created_at: string;
  resolved_at: string | null;
  resolution_card_id: number | null;
};

export type CardSearchResult = {
  id: number;
  title: string;
  year: number;
  card_number: string;
  brand: string;
  card_set: string;
  player: string;
  rookie_flag: boolean;
  valuation_preview: number | null;
  comp_count: number;
};

export type Valuation = {
  card_id: number;
  grade: string;
  estimated_price: number | null;
  low_estimate: number | null;
  high_estimate: number | null;
  confidence_score: number;
  exact_comp_count: number;
  similar_comp_count: number;
  method: string;
  reason_codes: string[];
  explanation: string;
  window_used: string | null;
  last_sale_at: string | null;
};

export type CardDetail = {
  metadata: {
    id: number;
    title: string;
    year: number;
    card_number: string;
    brand: string;
    card_set: string;
    player: string;
    sport: string | null;
    rookie_flag: boolean;
    autograph_flag: boolean;
    patch_flag: boolean;
  };
  valuation: Valuation;
  stats: { count: number; average_price: number | null; median_price: number | null; window: string };
  comparison: {
    raw_count: number;
    psa10_count: number;
    raw_median: number | null;
    psa10_median: number | null;
    grading_premium: number | null;
  };
  grades: { key: string; label: string; comp_count: number }[];
};

export type Comp = { id: number; sold_at: string; total_price: number; grade_value: string | null; grade_label: string };

export type SalesHistory = {
  price_series: { date: string; avg_price: number | null; median_price: number | null }[];
  volume_series: { date: string; sale_count: number }[];
};
