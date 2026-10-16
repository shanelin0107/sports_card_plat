// Filtering, grouping and sorting for the collection table. Pure functions, no React.
import type { Holding } from './types';

export type GroupBy = 'none' | 'player' | 'set' | 'year' | 'grade' | 'sport' | 'brand';
export type SortBy = 'newest' | 'value' | 'pnl' | 'pnl_pct' | 'paid' | 'player';
export type PnlFilter = 'all' | 'up' | 'down' | 'unpriced';

export type View = {
  q: string;
  grade: string; // 'all' | 'raw' | 'graded' | a grade label such as 'PSA 10'
  sport: string; // 'all' | sport name
  year: string; // 'all' | '2024'
  set: string; // 'all' | set name
  pnl: PnlFilter;
  rookie: boolean;
  group: GroupBy;
  sort: SortBy;
};

export const DEFAULT_VIEW: View = {
  q: '',
  grade: 'all',
  sport: 'all',
  year: 'all',
  set: 'all',
  pnl: 'all',
  rookie: false,
  group: 'none',
  sort: 'newest',
};

export const GROUP_LABELS: Record<GroupBy, string> = {
  none: 'No grouping',
  player: 'Player',
  set: 'Set',
  year: 'Year',
  grade: 'Grade',
  sport: 'Sport',
  brand: 'Brand',
};

export const SORT_LABELS: Record<SortBy, string> = {
  newest: 'Newest first',
  value: 'Est. value',
  pnl: 'P&L ($)',
  pnl_pct: 'P&L (%)',
  paid: 'Paid',
  player: 'Player A–Z',
};

const KEYS = Object.keys(DEFAULT_VIEW) as (keyof View)[];

/** Read a view from the URL (?group=player&grade=PSA+10 …); unknown values fall back to defaults. */
export function viewFromParams(p: URLSearchParams): View {
  const v: View = { ...DEFAULT_VIEW };
  const str = (k: 'q' | 'grade' | 'sport' | 'year' | 'set') => p.get(k) ?? DEFAULT_VIEW[k];
  v.q = str('q');
  v.grade = str('grade');
  v.sport = str('sport');
  v.year = str('year');
  v.set = str('set');
  const pnl = p.get('pnl');
  if (pnl === 'up' || pnl === 'down' || pnl === 'unpriced') v.pnl = pnl;
  v.rookie = p.get('rookie') === '1';
  const g = p.get('group') as GroupBy | null;
  if (g && g in GROUP_LABELS) v.group = g;
  const s = p.get('sort') as SortBy | null;
  if (s && s in SORT_LABELS) v.sort = s;
  return v;
}

/** Only non-default values go in the URL, so a plain /collection stays plain. */
export function viewToQuery(v: View): string {
  const p = new URLSearchParams();
  for (const k of KEYS) {
    const val = v[k];
    if (val === DEFAULT_VIEW[k]) continue;
    p.set(k, typeof val === 'boolean' ? (val ? '1' : '0') : String(val));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function isFiltered(v: View): boolean {
  return KEYS.some((k) => k !== 'group' && k !== 'sort' && v[k] !== DEFAULT_VIEW[k]);
}

function haystack(h: Holding): string {
  return [h.player, h.title, h.card_set, h.brand, h.card_number, h.parallel, h.year, h.grade_label, h.notes, h.sport]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

export function applyFilters(items: Holding[], v: View): Holding[] {
  const words = v.q.toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter((h) => {
    if (words.length) {
      const hay = haystack(h);
      if (!words.every((w) => hay.includes(w.replace(/^#/, '')))) return false;
    }
    if (v.grade === 'raw' && h.grade_value) return false;
    if (v.grade === 'graded' && !h.grade_value) return false;
    if (v.grade !== 'all' && v.grade !== 'raw' && v.grade !== 'graded' && h.grade_label !== v.grade) return false;
    if (v.sport !== 'all' && (h.sport ?? 'Unknown') !== v.sport) return false;
    if (v.year !== 'all' && String(h.year ?? '') !== v.year) return false;
    if (v.set !== 'all' && (h.card_set ?? 'Unknown') !== v.set) return false;
    if (v.rookie && !h.rookie_flag) return false;
    if (v.pnl === 'up' && !((h.unrealized_pnl ?? 0) > 0)) return false;
    if (v.pnl === 'down' && !((h.unrealized_pnl ?? 0) < 0)) return false;
    if (v.pnl === 'unpriced' && h.estimated_value !== null) return false;
    return true;
  });
}

export function sortItems(items: Holding[], by: SortBy): Holding[] {
  if (by === 'newest') return items; // the API already returns newest first
  const num = (x: number | null | undefined) => (x === null || x === undefined ? -Infinity : x);
  const out = [...items];
  if (by === 'player') out.sort((a, b) => (a.player ?? '').localeCompare(b.player ?? ''));
  else if (by === 'value') out.sort((a, b) => num(b.estimated_value) - num(a.estimated_value));
  else if (by === 'pnl') out.sort((a, b) => num(b.unrealized_pnl) - num(a.unrealized_pnl));
  else if (by === 'pnl_pct') out.sort((a, b) => num(b.unrealized_pnl_pct) - num(a.unrealized_pnl_pct));
  else if (by === 'paid') out.sort((a, b) => b.purchase_price * b.quantity - a.purchase_price * a.quantity);
  return out;
}

export type Totals = { count: number; qty: number; cost: number; est: number; pnl: number; unpriced: number };

export function totals(items: Holding[]): Totals {
  let cost = 0;
  let est = 0;
  let qty = 0;
  let unpriced = 0;
  let pricedCost = 0;
  for (const h of items) {
    const c = h.purchase_price * h.quantity;
    cost += c;
    qty += h.quantity;
    if (h.estimated_value === null) unpriced += 1;
    else {
      est += h.estimated_value;
      pricedCost += c;
    }
  }
  // P&L only over cards that have an estimate; an unpriced card isn't a loss.
  return { count: items.length, qty, cost, est, pnl: est - pricedCost, unpriced };
}

export type Group = { key: string; label: string; items: Holding[]; totals: Totals };

function groupKey(h: Holding, by: GroupBy): string {
  switch (by) {
    case 'player':
      return h.player ?? 'Unknown player';
    case 'set':
      return [h.year, h.card_set].filter(Boolean).join(' ') || 'Unknown set';
    case 'year':
      return h.year ? String(h.year) : 'Unknown year';
    case 'grade':
      return h.grade_label || 'Raw';
    case 'sport':
      return h.sport ?? 'Unknown sport';
    case 'brand':
      return h.brand ?? 'Unknown brand';
    default:
      return 'All';
  }
}

/** Groups keep the items' order; groups themselves are ordered by estimated value (biggest first),
 *  except years (newest first) and grades (Raw, then best grade first). */
export function groupItems(items: Holding[], by: GroupBy): Group[] {
  if (by === 'none') return [{ key: 'all', label: 'All', items, totals: totals(items) }];
  const map = new Map<string, Holding[]>();
  for (const h of items) {
    const k = groupKey(h, by);
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(h);
  }
  const groups = [...map.entries()].map(([key, list]) => ({ key, label: key, items: list, totals: totals(list) }));
  if (by === 'year') groups.sort((a, b) => b.key.localeCompare(a.key));
  else if (by === 'grade') {
    const rank = (k: string) => (k === 'Raw' ? -Infinity : -parseFloat(k.split(' ').pop() ?? '0'));
    groups.sort((a, b) => rank(a.key) - rank(b.key) || a.key.localeCompare(b.key));
  } else groups.sort((a, b) => b.totals.est - a.totals.est || a.label.localeCompare(b.label));
  return groups;
}

/** Distinct values for the filter dropdowns, from what's actually in the collection. */
export function filterOptions(items: Holding[]) {
  const uniq = (xs: (string | null | undefined)[]) => [...new Set(xs.filter((x): x is string => Boolean(x)))];
  return {
    grades: uniq(items.filter((h) => h.grade_value).map((h) => h.grade_label)).sort(
      (a, b) => parseFloat(b.split(' ').pop() ?? '0') - parseFloat(a.split(' ').pop() ?? '0') || a.localeCompare(b),
    ),
    sports: uniq(items.map((h) => h.sport)).sort(),
    years: uniq(items.map((h) => (h.year ? String(h.year) : null))).sort((a, b) => b.localeCompare(a)),
    sets: uniq(items.map((h) => h.card_set)).sort(),
  };
}
