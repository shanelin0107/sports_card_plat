// Insert / SSP set guide: types and pull-odds math. Pure functions, no React.

export type BoxType = { id: number; name: string; packs_per_box: number | null; cards_per_pack: number | null; boxes_per_case: number | null };
export type SetParallel = { id: number; name: string; print_run: number | null; odds: Record<string, number> };
export type CardPrice = { count: number; median: number | null; last: number | null; last_date: string | null; fetched_at: string | null };
export type SetCard = {
  id: number;
  number: string;
  player: string;
  team: string | null;
  rookie: boolean;
  image_url: string | null;
  image_crop: number[] | null;
  image_locked: boolean;
  owned: number;
  prices: Record<string, CardPrice>; // by parallel id
};
export type SetInsert = {
  id: number;
  name: string;
  code: string | null;
  kind: string;
  note: string | null;
  photos_checked_at: string | null;
  parallels: SetParallel[];
  cards: SetCard[];
};
export type SetProduct = {
  id: number;
  name: string;
  sport: string;
  year: number;
  brand: string;
  set_name: string;
  checklist_url: string | null;
  odds_url: string | null;
  source_note: string | null;
  imported_at: string;
  box_types: BoxType[];
  inserts: SetInsert[];
};
export type SetSummary = { id: number; name: string; sport: string; year: number; inserts: number; cards: number; imported_at: string };

export type PriceResult = {
  query: string;
  days: number | null;
  count: number;
  searched: number;
  items: { item_id: string; title: string; price: number; shipping: number; total: number; date: string; url: string; image: string | null; best_offer: boolean; grade: string }[];
  stats: { count: number; low: number; median: number; high: number } | null;
  last_sale: { total: number; date: string } | null;
  left_out?: { title: string; total: number; date: string | null; url: string; why: string }[];
  cached: boolean;
  stale?: string; // a fresh lookup failed (quota / CompsAPI down): this is the last saved result
  fetched_at: string;
};

export type BoxOdds = {
  packs: number; // 1 in N packs
  perBox: number | null; // chance of at least one in a box (0–1)
  boxesPerHit: number | null; // about one every N boxes
  perCase: number | null; // expected hits per case
};

/** "1:N packs" -> chance per box, boxes per hit, hits per case. */
export function boxOdds(packs: number | undefined, box: BoxType): BoxOdds | null {
  if (!packs) return null;
  const ppb = box.packs_per_box;
  if (!ppb) return { packs, perBox: null, boxesPerHit: null, perCase: null };
  const perBox = 1 - Math.pow(1 - 1 / packs, ppb);
  const boxesPerHit = packs / ppb;
  return { packs, perBox, boxesPerHit, perCase: box.boxes_per_case ? box.boxes_per_case / boxesPerHit : null };
}

export function fmtPct(p: number | null): string {
  if (p === null) return '—';
  if (p >= 0.995) return '~100%';
  if (p >= 0.1) return `${Math.round(p * 100)}%`;
  if (p >= 0.01) return `${(p * 100).toFixed(1)}%`;
  return `${(p * 100).toFixed(2)}%`;
}

export function fmtBoxes(n: number | null): string {
  if (n === null) return '—';
  if (n <= 1) return 'every box';
  if (n < 10) return `1 in ${n.toFixed(1)} boxes`;
  return `1 in ${Math.round(n).toLocaleString()} boxes`;
}

export function fmtPacks(n: number): string {
  return `1:${n.toLocaleString()}`;
}

export const baseParallel = (ins: SetInsert) => ins.parallels.find((p) => p.name.toLowerCase() === 'base') ?? ins.parallels[0];

/** The parallel as it's named on the card and in your collection: "Fanatical Gold". */
export function parallelLabel(ins: SetInsert, par: SetParallel): string {
  return par.name.toLowerCase() === 'base' ? ins.name : `${ins.name} ${par.name}`;
}
