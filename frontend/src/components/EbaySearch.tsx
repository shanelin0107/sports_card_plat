'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money } from '@/lib/format';
import type { CardSearchResult } from '@/lib/types';

import { AddFromListing } from './AddFromListing';

/** One eBay item: a sold listing (search page) or a live one (fallback without CompsAPI). */
export type SearchListing = {
  item_id: string;
  title: string;
  price: number; // item price (live: asking price)
  shipping?: number | null;
  url: string;
  image?: string | null;
  buying_options?: string[];
  bid_count?: number | null;
  grade: string;
  // sold listings only
  sold?: boolean;
  date?: string | null;
  total?: number; // price + shipping
  best_offer?: boolean;
};

type Stats = { count: number; low: number; median: number; high: number } | null;
type SoldResult = {
  query: string;
  searched_for?: string;
  must_include?: string[];
  days: number | null;
  count: number;
  items: SoldRow[];
  stats: Stats;
  last_sale: SoldRow | null;
  cached: boolean;
};
type SoldRow = { item_id: string; title: string; price: number; shipping: number; total: number; date: string; url: string; image: string | null; best_offer: boolean; grade: string };
type LiveResult = { query: string; active: SearchListing[]; total_found: number | null };

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'raw', label: 'Raw' },
  { key: 'graded', label: 'Graded' },
  { key: 'psa10', label: 'PSA 10' },
  { key: 'psa9', label: 'PSA 9' },
] as const;

function keep(filter: string, grade: string) {
  if (filter === 'all') return true;
  if (filter === 'raw') return grade === 'Raw';
  if (filter === 'graded') return grade !== 'Raw';
  return grade.replace(' ', '').toLowerCase() === filter;
}

function median(xs: number[]) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const soldToListing = (r: SoldRow): SearchListing => ({
  item_id: r.item_id,
  title: r.title,
  price: r.price,
  shipping: r.shipping,
  url: r.url,
  image: r.image,
  grade: r.grade,
  sold: true,
  date: r.date,
  total: r.total,
  best_offer: r.best_offer,
});

export function EbaySearch({ q, owned }: { q: string; owned: CardSearchResult[] }) {
  const [items, setItems] = useState<SearchListing[] | null>(null);
  const [mode, setMode] = useState<'sold' | 'live'>('sold');
  const [meta, setMeta] = useState<{ days: number | null; cached: boolean; total_found: number | null; searched?: string; must?: string[] }>({
    days: null,
    cached: false,
    total_found: null,
  });
  const [err, setErr] = useState<string | null>(null);
  const [off, setOff] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [adding, setAdding] = useState<SearchListing | null>(null);

  useEffect(() => {
    if (!q) return;
    let cancelled = false;
    setItems(null);
    setErr(null);
    setOff(false);
    const enc = encodeURIComponent(q);
    api<SoldResult>(`/market/sold-search?q=${enc}`)
      .then((r) => {
        if (cancelled) return;
        setMode('sold');
        setMeta({ days: r.days, cached: r.cached, total_found: null, searched: r.searched_for, must: r.must_include });
        setItems(r.items.map(soldToListing));
      })
      .catch((e: Error) => {
        if (cancelled) return;
        if (!e.message.includes('compsapi_off')) return setErr(e.message);
        // No CompsAPI key: show live listings instead, so the page still works.
        api<LiveResult>(`/market/ebay/listings?q=${enc}`)
          .then((r) => {
            if (cancelled) return;
            setMode('live');
            setMeta({ days: null, cached: false, total_found: r.total_found });
            setItems(r.active);
          })
          .catch((e2: Error) => (e2.message.includes('eBay is off') ? setOff(true) : setErr(e2.message)));
      });
    return () => {
      cancelled = true;
    };
  }, [q]);

  const shown = useMemo(() => (items ?? []).filter((l) => keep(filter, l.grade)), [items, filter]);
  const sold = mode === 'sold';
  const prices = shown.map((l) => (sold ? (l.total ?? l.price) : l.price));
  const last = sold ? shown[0] : undefined; // sold results come newest first

  if (!q) {
    return (
      <div className="panel p-6">
        <p className="font-bold">Look up what a card sells for</p>
        <p className="mt-1 text-[13px] text-muted">
          Type what’s printed on the card — year, set, player, number, parallel — e.g. <span className="font-mono text-ink">2024-25 prizm black lillard orange wave</span>.
          You’ll see recent eBay <b>sold</b> prices; press <b>Add to collection</b> on the matching one. Live listings are on each card’s page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {owned.length > 0 && (
        <section className="panel p-4" aria-label="Already in your catalog">
          <p className="eyebrow mb-2">Already in your catalog</p>
          <ul className="flex flex-wrap gap-2">
            {owned.slice(0, 8).map((c) => (
              <li key={c.id}>
                <Link href={`/cards/${c.id}`} className="flex min-h-11 items-center rounded-md bg-raised px-3 text-[13px] text-ink hover:text-link">
                  {c.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {off && (
        <div className="panel p-5 text-[13px] text-muted">
          Sold prices need a CompsAPI key: add <code className="font-mono text-ink">COMPSAPI_KEY</code> to <code className="font-mono text-ink">.env</code> and restart
          (free key at app.compsapi.com).
        </div>
      )}
      {err && <div className="panel p-5 text-[13px] text-down">Search failed: {err}</div>}
      {!items && !off && !err && <p className="text-muted">Looking up eBay sales…</p>}

      {items && (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="grid grid-cols-2 gap-2 font-mono text-[12px] sm:grid-cols-4 lg:w-[720px]">
              <div className="tile">
                <span className="text-muted">{sold ? 'Sales' : 'Listings'}</span>
                <br />
                <b className="text-[16px]">{shown.length}</b>
                {!sold && meta.total_found ? <span className="text-muted"> of {meta.total_found}</span> : null}
              </div>
              <div className="tile">
                <span className="text-muted">{sold ? 'Median sold' : 'Median ask'}</span>
                <br />
                <b className="text-[16px]">{money(median(prices))}</b>
              </div>
              {sold ? (
                <div className="tile">
                  <span className="text-muted">Last sale</span>
                  <br />
                  <b className="text-[16px] text-up">{money(last?.total ?? null)}</b>
                  {last?.date && <span className="block text-[11px] text-muted">{longDate(last.date)}</span>}
                </div>
              ) : (
                <div className="tile">
                  <span className="text-muted">Lowest ask</span>
                  <br />
                  <b className="text-[16px] text-up">{money(prices.length ? Math.min(...prices) : null)}</b>
                </div>
              )}
              <div className="tile">
                <span className="text-muted">Range</span>
                <br />
                <b className="text-[16px]">{prices.length ? `${money(Math.min(...prices), { whole: true })}–${money(Math.max(...prices), { whole: true })}` : '—'}</b>
              </div>
            </div>
            <div role="tablist" aria-label="Grade filter" className="flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  role="tab"
                  aria-selected={filter === f.key}
                  onClick={() => setFilter(f.key)}
                  className={`min-h-11 rounded-md px-3 font-mono text-[12px] ${filter === f.key ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          {sold && meta.searched && (
            <p className="font-mono text-[12px] text-muted">
              Searched eBay sold for <span className="text-ink">“{meta.searched}”</span>
              {meta.must?.length ? (
                <>
                  {' '}
                  · titles must also have <span className="text-ink">{meta.must.join(', ')}</span>
                </>
              ) : null}{' '}
              <span className="font-sans">(words sellers often leave out — RC, Auto, Refractor, card codes — aren’t required)</span>
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[12px] text-muted">
              {sold
                ? `eBay sold listings${meta.days ? `, last ${meta.days >= 365 ? `${Math.round(meta.days / 365)} year` : `${meta.days} days`}` : ''}, newest first. Prices include shipping; Best Offer sales show the accepted price. Lots and breaks are left out.${meta.cached ? ' (Saved result — no search used.)' : ' Each new search uses 1 CompsAPI search.'} Live listings are on each card’s page.`
                : 'These are live listings (asking prices) — sold prices appear once a CompsAPI key is set.'}
            </p>
            <Link href={`/collection?new=${encodeURIComponent(q)}`} className="btn-ghost text-[13px] text-ink">
              Your exact card isn’t here? Add it manually →
            </Link>
          </div>

          {shown.length === 0 ? (
            <div className="panel space-y-3 p-5">
              <p className="text-muted">
                {sold ? 'No sales match.' : 'No listings match.'} Try fewer words (drop the serial number or grade) — or add the card yourself.
              </p>
              <Link href={`/collection?new=${encodeURIComponent(q)}`} className="btn-primary text-[#06281A] hover:text-[#06281A]">
                + Add “{q}” manually
              </Link>
            </div>
          ) : (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
              {shown.map((l) => (
                <li key={l.item_id} className="panel flex flex-col overflow-hidden">
                  <a href={l.url} target="_blank" rel="noopener noreferrer nofollow" className="relative block bg-base" title={sold ? 'View the sold listing on eBay' : 'View on eBay'}>
                    {l.image ? (
                      // eslint-disable-next-line @next/next/no-img-element -- remote eBay images
                      <img src={l.image} alt={l.title} loading="lazy" className="aspect-[5/7] w-full object-contain" />
                    ) : (
                      <div className="flex aspect-[5/7] items-center justify-center text-[12px] text-muted">No photo</div>
                    )}
                    {sold && <span className="badge absolute left-2 top-2 bg-up/15 text-up">SOLD</span>}
                  </a>
                  <div className="flex flex-1 flex-col gap-2 p-3">
                    <p className="line-clamp-3 text-[12px] leading-snug" title={l.title}>
                      {l.title}
                    </p>
                    <div className="mt-auto font-mono">
                      <div className="flex items-baseline justify-between">
                        <b className="text-[16px]">{money(sold ? (l.total ?? l.price) : l.price)}</b>
                        <span className="text-[11px] text-muted">{l.grade}</span>
                      </div>
                      <p className="text-[11px] text-muted">
                        {sold
                          ? `${l.date ? longDate(l.date) : ''}${l.best_offer ? ' · best offer' : ''}${l.shipping ? ` · incl. ${money(l.shipping)} ship` : ''}`
                          : l.buying_options?.includes('AUCTION')
                            ? `auction${l.bid_count ? ` · ${l.bid_count} bids` : ''}`
                            : 'buy now'}
                      </p>
                    </div>
                    <button className="btn-primary w-full" onClick={() => setAdding(l)}>
                      + Add to collection
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {adding && <AddFromListing listing={adding} onClose={() => setAdding(null)} />}
    </div>
  );
}
