'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money } from '@/lib/format';
import { parallelLabel, type PriceResult, type SetCard, type SetInsert, type SetParallel, type SetProduct } from '@/lib/sets';
import type { CompsApiStatus } from '@/lib/types';

import { AddFromListing } from './AddFromListing';
import { CardPhoto } from './SetCardImage';
import type { SearchListing } from './EbaySearch';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'raw', label: 'Raw' },
  { key: 'graded', label: 'Graded' },
  { key: 'psa10', label: 'PSA 10' },
] as const;

function keep(filter: string, grade: string) {
  if (filter === 'all') return true;
  if (filter === 'raw') return grade === 'Raw';
  if (filter === 'graded') return grade !== 'Raw';
  return grade.replace(' ', '').toLowerCase() === filter;
}

/** Same eBay photo at a different size (…/s-l225.jpg vs …/s-l500.jpg)? */
const samePhoto = (a: string | null, b: string | null) => Boolean(a && b && a.replace(/\/s-l\d+\./, '/') === b.replace(/\/s-l\d+\./, '/'));

function median(xs: number[]) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Side panel: sold prices for one checklist card in one parallel (looked up on open). */
export function SetPricePanel({
  product,
  ins,
  card,
  parallel,
  onParallel,
  onResult,
  onPhotoChanged,
  onClose,
}: {
  product: SetProduct;
  ins: SetInsert;
  card: SetCard;
  parallel: SetParallel;
  onParallel: (id: number) => void;
  onResult: (r: PriceResult, parallelId: number) => void;
  onPhotoChanged: () => Promise<void>;
  onClose: () => void;
}) {
  const [res, setRes] = useState<PriceResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('all');
  const [quota, setQuota] = useState<CompsApiStatus | null>(null);
  const [adding, setAdding] = useState<SearchListing | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);
  const [photo, setPhoto] = useState<{ url: string | null; crop: number[] | null }>({ url: card.image_url, crop: card.image_crop });
  const [photoBusy, setPhotoBusy] = useState<string | null>(null);

  async function choosePhoto(url: string) {
    setPhotoBusy(url);
    try {
      const r = await api<{ url: string | null; crop: number[] | null }>(`/sets/cards/${card.id}/photo`, { method: 'PUT', body: JSON.stringify({ url }) });
      setPhoto(r);
      await onPhotoChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPhotoBusy(null);
    }
  }

  const latest = useRef(0); // only the newest lookup may update the panel (parallel switched mid-request)

  function load(force: boolean) {
    const id = ++latest.current;
    const parId = parallel.id;
    setBusy(true);
    setErr(null);
    if (force) setRes(null);
    api<PriceResult>(`/sets/cards/${card.id}/price?parallel_id=${parId}${force ? '&force=true' : ''}`, { method: 'POST' })
      .then((r) => {
        onResult(r, parId); // the grid keeps it under its own parallel either way
        if (id !== latest.current) return;
        setRes(r);
        if (!r.cached) api<CompsApiStatus>('/market/compsapi/status').then(setQuota).catch(() => {});
      })
      .catch((e: Error) => {
        if (id === latest.current) setErr(e.message);
      })
      .finally(() => {
        if (id === latest.current) setBusy(false);
      });
  }

  useEffect(() => {
    ref.current?.focus();
    setRes(null);
    setFilter('all');
    load(false);
    api<CompsApiStatus>('/market/compsapi/status').then(setQuota).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per card+parallel
  }, [card.id, parallel.id]);

  const shown = useMemo(() => (res?.items ?? []).filter((i) => keep(filter, i.grade)), [res, filter]);
  const totals = shown.map((i) => i.total);
  const last = shown[0];
  const left = quota && typeof quota.monthly_quota === 'number' && typeof quota.monthly_used === 'number' ? quota.monthly_quota - quota.monthly_used : null;
  const label = parallelLabel(ins, parallel);

  function addToCollection() {
    const sale = shown[0];
    const title = `${product.year} ${product.set_name} ${label} ${card.player} ${card.number}${parallel.print_run ? ` /${parallel.print_run}` : ''}`;
    const listing: SearchListing = sale
      ? { item_id: sale.item_id, title: sale.title, price: sale.price, shipping: sale.shipping, url: sale.url, image: sale.image, grade: sale.grade, sold: true, date: sale.date, total: sale.total, best_offer: sale.best_offer }
      : { item_id: `set-${card.id}-${parallel.id}`, title, price: 0, url: `https://www.ebay.com/sch/i.html?q=${encodeURIComponent(title)}`, image: card.image_url, grade: 'Raw' };
    setAdding(listing);
  }

  const offKey = err?.includes('compsapi_off');

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`${card.player} ${label} sold prices`}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && !adding && onClose()}
        className="flex h-full w-full max-w-[560px] flex-col overflow-y-auto border-l border-edge bg-panel outline-none motion-safe:animate-[fadein_120ms_ease-out]"
      >
        <div className="panel-head sticky top-0 z-10 bg-panel">
          <div className="min-w-0">
            <p className="font-mono text-[11px] text-muted">
              {card.number} · {product.name}
            </p>
            <h2 className="truncate text-[16px] font-bold">
              {card.player} {card.rookie && <span className="badge bg-warn/20 text-warn">RC</span>}
            </h2>
          </div>
          <button className="btn-ghost px-3" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div className="flex gap-4">
            {(photo.url || last?.image) && (
              <div className="w-[120px] shrink-0 overflow-hidden rounded border border-edge bg-base">
                <CardPhoto src={photo.url ?? last?.image ?? null} crop={photo.url ? photo.crop : null} fallback={null} />
              </div>
            )}
            <div className="min-w-0 space-y-2">
              <p className="text-[13px]">
                {card.team}
                {card.owned > 0 && <span className="ml-2 badge bg-up/20 text-up">✓ You have {card.owned}</span>}
              </p>
              <div role="tablist" aria-label="Parallel" className="flex flex-wrap gap-1">
                {ins.parallels.map((p) => (
                  <button
                    key={p.id}
                    role="tab"
                    aria-selected={p.id === parallel.id}
                    onClick={() => onParallel(p.id)}
                    className={`min-h-9 rounded px-2.5 font-mono text-[12px] ${p.id === parallel.id ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
                  >
                    {p.name}
                    {p.print_run ? (p.print_run === 1 ? ' 1/1' : ` /${p.print_run}`) : ''}
                  </button>
                ))}
              </div>
              <button className="btn-primary" onClick={addToCollection}>
                + Add to collection
              </button>
            </div>
          </div>

          {busy && !res && <p className="text-[13px] text-muted">Looking up eBay sales for {label}… (a saved result is used if there is one)</p>}
          {err && (
            <div className="rounded-md border border-down/40 p-3 text-[13px]">
              {offKey ? (
                <span className="text-muted">
                  Price checks need a CompsAPI key: add <code className="font-mono text-ink">COMPSAPI_KEY</code> to <code className="font-mono text-ink">.env</code> and restart.
                </span>
              ) : (
                <span className="text-down">
                  {err.includes('quota')
                    ? 'This month’s CompsAPI searches are used up (they reset on the 1st). Cards you already looked up still show their saved prices.'
                    : `Lookup failed: ${err}`}
                </span>
              )}
            </div>
          )}

          {res && (
            <>
              <div className="grid grid-cols-2 gap-2 font-mono text-[12px] sm:grid-cols-4">
                <div className="tile">
                  <span className="text-muted">Sales</span>
                  <br />
                  <b className="text-[16px]">{shown.length}</b>
                </div>
                <div className="tile">
                  <span className="text-muted">Median</span>
                  <br />
                  <b className="text-[16px]">{money(median(totals))}</b>
                </div>
                <div className="tile">
                  <span className="text-muted">Last sale</span>
                  <br />
                  <b className="text-[16px] text-up">{money(last?.total ?? null)}</b>
                  {last?.date && <span className="block text-[11px] text-muted">{longDate(last.date)}</span>}
                </div>
                <div className="tile">
                  <span className="text-muted">Range</span>
                  <br />
                  <b className="text-[14px]">{totals.length ? `${money(Math.min(...totals), { whole: true })}–${money(Math.max(...totals), { whole: true })}` : '—'}</b>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <div role="tablist" aria-label="Grade filter" className="flex flex-wrap gap-1">
                  {FILTERS.map((f) => (
                    <button
                      key={f.key}
                      role="tab"
                      aria-selected={filter === f.key}
                      onClick={() => setFilter(f.key)}
                      className={`min-h-9 rounded-md px-3 font-mono text-[12px] ${filter === f.key ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
                <button className="btn-ghost min-h-9 px-3 text-[12px]" onClick={() => load(true)} disabled={busy} title="Search eBay sold again (uses 1 CompsAPI search)">
                  {busy ? 'Searching…' : '↻ Refresh'}
                </button>
              </div>

              <p className="text-[11px] text-muted">
                {res.outdated ? 'Saved before the matching rules were improved — press ↻ Refresh to redo it (1 search). ' : ''}{res.stale ? `Couldn’t search again (${res.stale.includes('quota') ? 'monthly CompsAPI searches are used up' : 'CompsAPI is busy'}) — showing the result saved ${longDate(res.fetched_at)}. ` : res.cached ? `Saved result from ${longDate(res.fetched_at)} — no search used. ` : 'Used 1 CompsAPI search. '}
                {left !== null ? `${left} left this month. ` : ''}
                Searched “{res.query}”: {res.searched} sold listings, {res.count} are this exact card and parallel
                {res.days ? ` (last ${res.days >= 365 ? `${Math.round(res.days / 365)} year` : `${res.days} days`})` : ''}. Lots and breaks are left out.
              </p>

              {shown.length === 0 ? (
                <p className="text-[13px] text-muted">No sales of this card{filter !== 'all' ? ' in this grade' : ''} yet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {shown.map((i) => (
                    <li key={i.item_id} className="flex gap-3 py-2.5">
                      {i.image ? (
                        // eslint-disable-next-line @next/next/no-img-element -- remote eBay images
                        <img src={i.image} alt="" loading="lazy" className="h-14 w-10 shrink-0 rounded-[3px] border border-edge object-cover" />
                      ) : (
                        <div className="h-14 w-10 shrink-0 rounded-[3px] border border-edge bg-raised" />
                      )}
                      <div className="min-w-0 flex-1">
                        <a href={i.url} target="_blank" rel="noopener noreferrer nofollow" className="line-clamp-2 text-[12px] leading-snug text-ink hover:text-link">
                          {i.title}
                        </a>
                        <p className="font-mono text-[11px] text-muted">
                          {longDate(i.date)} · {i.grade}
                          {i.best_offer ? ' · best offer' : ''}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <b className="font-mono text-[14px]">{money(i.total)}</b>
                        {i.image && (
                          <button
                            type="button"
                            className="text-[11px] text-link hover:text-ink disabled:text-muted"
                            disabled={photoBusy !== null || samePhoto(photo.url, i.image)}
                            onClick={() => choosePhoto(i.image!)}
                          >
                            {photoBusy === i.image ? 'Saving…' : samePhoto(photo.url, i.image) ? '✓ Card photo' : 'Use as card photo'}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {res.left_out && res.left_out.length > 0 && (
                <details open={res.count === 0} className="rounded-md border border-line p-3 text-[12px]">
                  <summary className="cursor-pointer text-muted">
                    {res.searched - res.count} other sold listing{res.searched - res.count === 1 ? '' : 's'} the search found — left out (not this card)
                  </summary>
                  <ul className="mt-2 space-y-1.5">
                    {res.left_out.map((x, k) => (
                      <li key={k} className="flex gap-2">
                        <span className="w-[150px] shrink-0 font-mono text-[11px] text-warn">{x.why}</span>
                        <a href={x.url} target="_blank" rel="noopener noreferrer nofollow" className="min-w-0 flex-1 truncate text-ink hover:text-link" title={x.title}>
                          {x.title}
                        </a>
                        <span className="shrink-0 font-mono">{money(x.total)}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-[11px] text-muted">If one of these really is this card, take a screenshot of this list so the matching rule can be fixed.</p>
                </details>
              )}
            </>
          )}
        </div>
      </div>

      {adding && (
        <div onClick={(e) => e.stopPropagation()}>
          <AddFromListing
            listing={adding}
            onClose={() => setAdding(null)}
            card={{
              sport: product.sport,
              year: product.year,
              brand: product.brand,
              set_name: product.set_name,
              player: card.player,
              card_number: card.number,
              parallel: label,
              print_run: parallel.print_run,
              rookie: card.rookie,
              autograph: false,
            }}
          />
        </div>
      )}
    </div>
  );
}
