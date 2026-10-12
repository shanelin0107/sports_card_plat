const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export function money(v: number | null | undefined, opts: { whole?: boolean } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return (opts.whole ? usd0 : usd).format(v);
}

export function signedMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const s = money(Math.abs(v));
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const s = `${Math.abs(v).toFixed(1)}%`;
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}

export function tone(v: number | null | undefined): string {
  if (!v) return 'text-ink';
  return v > 0 ? 'text-up' : 'text-down';
}

// Sale dates are calendar dates stored as UTC midnight. Format everything in UTC so a
// sale on Mar 27 never shows as Mar 26 in US time zones, and server/browser agree.
function toDate(iso: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00Z`) : new Date(iso);
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = toDate(iso);
  return `${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return toDate(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
}

export function confidenceLabel(score: number | null | undefined): { label: string; cls: string } {
  if (score === null || score === undefined) return { label: '—', cls: 'text-muted' };
  if (score >= 0.7) return { label: 'High', cls: 'text-up' };
  if (score >= 0.45) return { label: 'Medium', cls: 'text-ink' };
  return { label: 'Low', cls: 'text-warn' };
}

/** "Victor Wembanyama" -> "WEMBANYAMA" for the ticker. */
export function tickerName(player: string | null): string {
  if (!player) return 'CARD';
  return player.split(' ').slice(-1)[0].toUpperCase();
}
