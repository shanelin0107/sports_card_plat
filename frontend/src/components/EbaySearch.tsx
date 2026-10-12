'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { api } from '@/lib/client-api';
import { money } from '@/lib/format';
import type { CardSearchResult } from '@/lib/types';

import { AddFromListing } from './AddFromListing';

export type SearchListing = {
  item_id: string;
  title: string;
  price: number;
  shipping?: number | null;
  url: string;
  image?: string | null;
  buying_options?: string[];
  bid_count?: number | null;
  grade: string;
};
type Result = {
  query: string;
  active: SearchListing[];
  active_stats: { count: number; low: number; median: number; high: number } | null;
  total_found: number | null;
};

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

export function EbaySearch({ q, owned }: { q: string; owned: CardSearchResult[] }) {
  const [data, setData] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [off, setOff] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [adding, setAdding] = useState<SearchListing | null>(null);

  useEffect(() => {
    if (!q) return;
    setData(null);
    setErr(null);
    api<Result>(`/market/ebay/listings?q=${encodeURIComponent(q)}`)
      .then(setData)
      .catch((e: Error) => (e.message.includes('eBay is off') ? setOff(true) : setErr(e.message)));
  }, [q]);

  const shown = useMemo(() => (data?.active ?? []).filter((l) => keep(filter, l.grade)), [data, filter]);
  const prices = shown.map((l) => l.price);

  if (!q) {
    return (
      <div className="panel p-6">
        <p className="font-bold">Search eBay for any card</p>
        <p className="mt-1 text-[13px] text-muted">
          Type what’s printed on the card — year, set, player, number, parallel — e.g. <span className="font-mono text-ink">2024-25 prizm black lillard orange wave</span>.
          Then press <b>Add to collection</b> on the matching listing.
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
          eBay search is off. Add <code className="font-mono text-ink">EBAY_CLIENT_ID</code> / <code className="font-mono text-ink">EBAY_CLIENT_SECRET</code> to{' '}
          <code className="font-mono text-ink">.env</code> and restart.
        </div>
      )}
      {err && <div className="panel p-5 text-[13px] text-down">eBay search failed: {err}</div>}
      {!data && !off && !err && <p className="text-muted">Searching eBay…</p>}

      {data && (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="grid grid-cols-3 gap-2 font-mono text-[12px] sm:w-[480px]">
              <div className="tile">
                <span className="text-muted">Listings</span>
                <br />
                <b className="text-[16px]">{shown.length}</b>
                {data.total_found ? <span className="text-muted"> of {data.total_found}</span> : null}
              </div>
              <div className="tile">
                <span className="text-muted">Lowest ask</span>
                <br />
                <b className="text-[16px] text-up">{money(prices.length ? Math.min(...prices) : null)}</b>
              </div>
              <div className="tile">
                <span className="text-muted">Median ask</span>
                <br />
                <b className="text-[16px]">{money(median(prices))}</b>
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[12px] text-muted">
              These are live listings (asking prices). Sold prices for a card appear on its page after you add it.
            </p>
            <Link href={`/collection?new=${encodeURIComponent(q)}`} className="btn-ghost text-[13px] text-ink">
              Your exact card isn’t listed? Add it manually →
            </Link>
          </div>

          {shown.length === 0 ? (
            <div className="panel space-y-3 p-5">
              <p className="text-muted">No listings match. Try fewer words (drop the serial number or grade) — or add the card yourself.</p>
              <Link href={`/collection?new=${encodeURIComponent(q)}`} className="btn-primary text-[#06281A] hover:text-[#06281A]">
                + Add “{q}” manually
              </Link>
            </div>
          ) : (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
              {shown.map((l) => (
                <li key={l.item_id} className="panel flex flex-col overflow-hidden">
                  <a href={l.url} target="_blank" rel="noopener noreferrer nofollow" className="block bg-base" title="View on eBay">
                    {l.image ? (
                      // eslint-disable-next-line @next/next/no-img-element -- remote eBay images
                      <img src={l.image} alt={l.title} loading="lazy" className="aspect-[5/7] w-full object-contain" />
                    ) : (
                      <div className="flex aspect-[5/7] items-center justify-center text-[12px] text-muted">No photo</div>
                    )}
                  </a>
                  <div className="flex flex-1 flex-col gap-2 p-3">
                    <p className="line-clamp-3 text-[12px] leading-snug" title={l.title}>
                      {l.title}
                    </p>
                    <div className="mt-auto flex items-baseline justify-between font-mono">
                      <b className="text-[16px]">{money(l.price)}</b>
                      <span className="text-[11px] text-muted">
                        {l.grade} · {l.buying_options?.includes('AUCTION') ? `auction${l.bid_count ? ` ${l.bid_count} bids` : ''}` : 'buy now'}
                      </span>
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
