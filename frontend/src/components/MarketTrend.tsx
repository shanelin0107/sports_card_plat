'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money, pct, shortDate, tone } from '@/lib/format';

import { FindSales } from './FindSales';

type Sale = {
  id: number;
  date: string;
  ts?: string;
  price: number;
  grade_label: string;
  source: string;
  url: string | null;
  title: string | null;
  rolling_median: number;
};
type Summary = {
  grade: string;
  window: string;
  median: number | null;
  low: number | null;
  high: number | null;
  count: number;
  prev_median: number | null;
  prev_count: number;
  change_pct: number | null;
  last_sale: Sale | null;
  sales: Sale[];
  volume: { date: string; count: number }[];
  trend?: { date: string; median: number; n: number }[];
  trend_days?: number;
  window_start: string | null;
  window_end: string;
};

const WINDOWS = ['30d', '90d', '1y', 'all'] as const;
const H_PRICE = 220;
const H_VOL = 56;
const PAD = { l: 8, r: 56, t: 12, b: 22 };

const DAY = 86400000;
const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
/** Where a sale sits on the time axis: its real time, or mid-day when only the date is known. */
const saleTime = (s: Sale) => {
  if (!s.ts) return day(s.date) + DAY / 2;
  const t = Date.parse(s.ts);
  return t % DAY === 0 ? t + DAY / 2 : t;
};

/** Round gridline values ($10, $20, $30 …) covering lo..hi, about `target` of them. */
function niceTicks(lo: number, hi: number, target = 4): number[] {
  const span = Math.max(hi - lo, 1);
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw) ?? 10 * mag;
  const out: number[] = [];
  const top = Math.ceil(hi / step - 1e-9) * step; // first gridline at or above the highest sale
  for (let v = Math.floor(lo / step) * step; v <= top + step * 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

/** Date labels along the x axis: every day/week/month depending on the span. */
function dateTicks(x0: number, x1: number): number[] {
  const days = (x1 - x0) / DAY;
  const step = [1, 2, 7, 14, 30, 61, 91, 182, 365].find((st) => days / st <= 6) ?? 365;
  const out: number[] = [];
  for (let t = x1; t >= x0 - 1; t -= step * DAY) out.unshift(t);
  return out;
}

export function MarketTrend({ cardId, grade }: { cardId: number; grade: string }) {
  const router = useRouter();
  const [win, setWin] = useState<(typeof WINDOWS)[number]>('30d');
  const [data, setData] = useState<Summary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<Sale | null>(null);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [confirm, setConfirm] = useState<number | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);
  // Draw at the container's real pixel width so text and dots never scale up.
  const box = useRef<HTMLDivElement | null>(null);
  const [W, setW] = useState(760);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [data?.sales.length]);

  const load = useCallback(() => {
    api<Summary>(`/cards/${cardId}/market-summary?grade=${grade}&window=${win}`)
      .then((d) => {
        setData(d);
        setErr(null);
      })
      .catch((e: Error) => setErr(e.message));
  }, [cardId, grade, win]);

  useEffect(load, [load]);

  // On open: pull eBay sold data, or (no sold access) let AI look for recent sales once a day.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const pollJob = (id: number) => {
      timer = setTimeout(async () => {
        try {
          const j = await api<{ status: string; result: { auto_saved?: number; sold?: unknown[] } | null; error_message: string | null }>(
            `/ai/price-research/${id}`,
          );
          if (cancelled) return;
          if (j.status === 'running') return pollJob(id);
          if (j.status === 'failed') return setSyncNote(`AI search failed: ${j.error_message}`);
          const n = j.result?.auto_saved ?? 0;
          setSyncNote(n > 0 ? `AI found and added ${n} sale${n > 1 ? 's' : ''}.` : 'AI searched the web but found no exact, dated sales for this card.');
          setSyncing(false);
          if (n > 0) {
            load();
            router.refresh();
          }
        } catch {
          setSyncing(false);
        }
      }, 4000);
    };
    api<{ status: string; added: number; research_id?: number; message?: string }>(`/market/sync/${cardId}?grade=${grade}`, { method: 'POST' })
      .then((r) => {
        if (cancelled) return;
        if (r.added > 0) {
          setSyncNote(`Added ${r.added} new eBay sale${r.added > 1 ? 's' : ''}.`);
          load();
          router.refresh();
        } else if ((r.status === 'ai_started' || r.status === 'ai_running') && r.research_id) {
          setSyncing(true);
          setSyncNote('No recent sales on file — AI is searching the web for this card’s sales (30–90 s)…');
          pollJob(r.research_id);
        } else if (r.status === 'ai_recent') {
          setSyncNote('AI already searched for this card’s sales in the last 24 hours.');
        } else if (r.status === 'quota') {
          setSyncNote('CompsAPI monthly quota is used up — new sales will load after it resets on the 1st.');
        } else if (r.status === 'no_sold_access') {
          setSyncNote('eBay doesn’t share sold history with your key, and AI price check is off.');
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per card/grade
  }, [cardId, grade]);

  async function removeSale(id: number) {
    setRemoving(id);
    try {
      await api(`/cards/${cardId}/comps/${id}`, { method: 'DELETE' });
      load();
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setRemoving(null);
      setConfirm(null);
    }
  }

  const geo = useMemo(() => {
    if (!data || data.sales.length === 0) return null;
    // Time axis runs from the start of the first day to the end of today.
    const x0 = data.window_start ? day(data.window_start) : day(data.sales[0].date);
    const x1 = Math.max(day(data.window_end), x0) + DAY;
    const prices = data.sales.map((s) => s.price);
    const lo = Math.min(...prices);
    const hi = Math.max(...prices);
    const padv = hi === lo ? hi * 0.1 || 1 : (hi - lo) * 0.08;
    const ticks = niceTicks(Math.max(0, lo - padv), hi + padv);
    const y0 = Math.min(ticks[0], lo);
    const y1 = Math.max(ticks[ticks.length - 1], hi);
    const xt = (t: number) => PAD.l + ((t - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
    const x = (iso: string) => xt(day(iso) + DAY / 2); // a calendar day's centre
    const y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H_PRICE - PAD.t - PAD.b);
    const maxVol = Math.max(...data.volume.map((v) => v.count), 1);
    const barW = Math.max(3, Math.min(14, ((W - PAD.l - PAD.r) / ((x1 - x0) / DAY)) * 0.7));
    // Sales known only by date share one spot; fan them out a little inside their day.
    const dayPx = (W - PAD.l - PAD.r) / ((x1 - x0) / DAY);
    const sameDay: Record<string, Sale[]> = {};
    for (const sl of data.sales) if (!sl.ts || Date.parse(sl.ts) % DAY === 0) (sameDay[sl.date] ??= []).push(sl);
    const cx: Record<number, number> = {};
    for (const sl of data.sales) {
      const group = sameDay[sl.date];
      const k = group ? group.indexOf(sl) : -1;
      const gap = group && group.length > 1 ? Math.min(7, (dayPx * 0.8) / (group.length - 1)) : 0;
      cx[sl.id] = xt(saleTime(sl)) + (k >= 0 ? (k - (group.length - 1) / 2) * gap : 0);
    }
    return { x, xt, y, cx, maxVol, barW, ticks, x0, x1, dates: dateTicks(x0, x1 - DAY) };
  }, [data, W]);

  return (
    <section className="panel" aria-label="Sales trend">
      <div className="panel-head flex-wrap">
        <div>
          <h2 className="panel-title">Sales trend · {data?.grade ?? '…'}</h2>
          <p className="text-[12px] text-muted">
            Dots = every recorded sale. Line = median of the last {data?.trend_days ?? 7} days. Bars = sales per day.
          </p>
        </div>
        <div role="tablist" aria-label="Window" className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w}
              role="tab"
              aria-selected={win === w}
              onClick={() => setWin(w)}
              className={`min-h-11 rounded-md px-3 font-mono text-[12px] uppercase ${win === w ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
            >
              {w}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4 p-5">
        {err && <p className="text-[13px] text-down">{err}</p>}
        {data && (
          <div className="grid grid-cols-2 gap-2 font-mono text-[12px] md:grid-cols-5">
            <Stat label={`Median · ${data.window.toUpperCase()}`} value={money(data.median)} big />
            <Stat label={`Sales · ${data.window.toUpperCase()}`} value={String(data.count)} sub={data.window !== 'all' ? `${data.prev_count} prior` : undefined} big />
            <Stat
              label="Change vs prior"
              value={data.change_pct !== null ? pct(data.change_pct) : '—'}
              valueClass={tone(data.change_pct)}
              sub={data.prev_median ? `prior median ${money(data.prev_median)}` : 'no prior sales'}
            />
            <Stat label="Range" value={data.low !== null ? `${money(data.low, { whole: true })}–${money(data.high, { whole: true })}` : '—'} />
            <Stat label="Last sale" value={money(data.last_sale?.price)} sub={data.last_sale ? longDate(data.last_sale.date) : undefined} />
          </div>
        )}

        <FindSales
          cardId={cardId}
          grade={grade}
          onAdded={() => {
            load();
            router.refresh();
          }}
        />

        {data && !geo && (
          <div className="flex h-[160px] flex-col items-center justify-center gap-1 rounded-md bg-base text-center text-[13px] text-muted">
            <p>No {data.grade} sales in the last {data.window === 'all' ? 'record' : data.window}.</p>
            <p className="text-[12px]">Open “eBay sold” above, then “+ Add a sale” for each one you want to count.</p>
            {data.window !== 'all' && (
              <button className="text-link hover:text-ink" onClick={() => setWin('all')}>
                Show all time →
              </button>
            )}
          </div>
        )}

        {data && geo && (
          <div className="relative" ref={box}>
            <svg viewBox={`0 0 ${W} ${H_PRICE + H_VOL}`} width={W} height={H_PRICE + H_VOL} role="img" aria-label={`${data.count} sales, median ${money(data.median)}`}>
              {geo.ticks.map((t) => (
                <g key={t}>
                  <line x1={PAD.l} x2={W - PAD.r} y1={geo.y(t)} y2={geo.y(t)} stroke="#1E2A36" />
                  <text x={W - PAD.r + 6} y={geo.y(t) + 3} fontSize="10" fill="#9FB3C8" fontFamily="JetBrains Mono">
                    {money(t, { whole: true })}
                  </text>
                </g>
              ))}
              {data.median !== null && (
                <g>
                  <line
                    x1={PAD.l}
                    x2={W - PAD.r}
                    y1={geo.y(data.median)}
                    y2={geo.y(data.median)}
                    stroke="#F5B841"
                    strokeDasharray="4 4"
                    opacity="0.7"
                  />
                  <text x={PAD.l + 2} y={geo.y(data.median) - 4} fontSize="10" fill="#F5B841" fontFamily="JetBrains Mono">
                    {`median ${money(data.median)}`}
                  </text>
                </g>
              )}
              {(data.trend?.length ?? 0) > 1 && (
                <polyline
                  points={data.trend!.map((t) => `${geo.x(t.date)},${geo.y(t.median)}`).join(' ')}
                  fill="none"
                  stroke="#3DDC97"
                  strokeWidth="2"
                  strokeLinejoin="round"
                />
              )}
              {data.sales.map((s) => (
                <circle
                  key={s.id}
                  cx={geo.cx[s.id]}
                  cy={geo.y(s.price)}
                  r={hover?.id === s.id ? 6 : 4}
                  fill={hover?.id === s.id ? '#3DDC97' : '#0B0F14'}
                  stroke="#7CC4FF"
                  strokeWidth="2"
                  onMouseEnter={() => setHover(s)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => s.url && window.open(s.url, '_blank', 'noopener')}
                  style={{ cursor: s.url ? 'pointer' : 'default' }}
                >
                  <title>{`${s.date} · ${money(s.price)} · ${s.grade_label} · ${s.source}`}</title>
                </circle>
              ))}
              {/* volume */}
              <line x1={PAD.l} x2={W - PAD.r} y1={H_PRICE + H_VOL - 4} y2={H_PRICE + H_VOL - 4} stroke="#1E2A36" />
              {data.volume.map((v) => {
                const h = (v.count / geo.maxVol) * (H_VOL - 18);
                return (
                  <rect key={v.date} x={geo.x(v.date) - geo.barW / 2} y={H_PRICE + H_VOL - 4 - h} width={geo.barW} height={h} fill="#263545" rx="1">
                    <title>{`${v.date}: ${v.count} sale${v.count > 1 ? 's' : ''}`}</title>
                  </rect>
                );
              })}
              {geo.dates.map((t, i) => {
                const iso = new Date(t).toISOString().slice(0, 10);
                const last = i === geo.dates.length - 1;
                return (
                  <text
                    key={t}
                    x={geo.x(iso)}
                    y={H_PRICE - 4}
                    textAnchor={last ? 'end' : 'middle'}
                    fontSize="10"
                    fill="#9FB3C8"
                    fontFamily="JetBrains Mono"
                  >
                    {shortDate(iso)}
                  </text>
                );
              })}
              <text x={W - PAD.r + 6} y={H_PRICE + H_VOL - 8} fontSize="10" fill="#9FB3C8" fontFamily="JetBrains Mono">
                vol
              </text>
            </svg>
            <div className="mt-1 min-h-[20px] font-mono text-[12px] text-muted" aria-live="polite">
              {hover
                ? `${longDate(hover.date)} · ${money(hover.price)} · ${hover.grade_label} · ${hover.source}${hover.url ? ' · click to open' : ''}`
                : 'Hover a dot for details · click to open the listing'}
            </div>
          </div>
        )}
        {syncNote && (
          <p className={`text-[12px] ${syncing ? 'text-warn' : 'text-muted'}`} role="status">
            {syncNote}
          </p>
        )}

        {data && data.sales.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Sales in this window ({data.sales.length})</p>
            <div className="overflow-x-auto rounded-md border border-line">
              <table className="w-full min-w-[560px] border-collapse text-[12px]">
                <tbody>
                  {[...data.sales].reverse().map((s) => (
                    <tr key={s.id} className="border-t border-line first:border-0">
                      <td className="py-2 pl-3 pr-2 font-mono text-muted">{longDate(s.date)}</td>
                      <td className="px-2">
                        {s.url ? (
                          <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="text-ink hover:text-link">
                            {s.source}
                          </a>
                        ) : (
                          s.source
                        )}
                        {s.title && <span className="block max-w-[360px] truncate text-muted">{s.title}</span>}
                      </td>
                      <td className="px-2 font-mono">{s.grade_label}</td>
                      <td className="px-2 text-right font-mono text-[13px]">{money(s.price)}</td>
                      <td className="py-2 pl-2 pr-3 text-right">
                        {confirm === s.id ? (
                          <span className="inline-flex gap-1">
                            <button className="btn-danger min-h-9 px-2 text-[12px]" disabled={removing === s.id} onClick={() => removeSale(s.id)}>
                              Remove
                            </button>
                            <button className="btn-ghost min-h-9 px-2 text-[12px]" onClick={() => setConfirm(null)}>
                              Keep
                            </button>
                          </span>
                        ) : (
                          <button className="min-h-9 px-2 text-[12px] text-muted hover:text-down" onClick={() => setConfirm(s.id)} aria-label={`Remove sale on ${s.date}`}>
                            Wrong sale?
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value, sub, big, valueClass = '' }: { label: string; value: string; sub?: string; big?: boolean; valueClass?: string }) {
  return (
    <div className="tile">
      <span className="text-muted">{label}</span>
      <br />
      <b className={`${big ? 'text-[20px]' : 'text-[15px]'} ${valueClass}`}>{value}</b>
      {sub && <span className="block text-[11px] text-muted">{sub}</span>}
    </div>
  );
}
