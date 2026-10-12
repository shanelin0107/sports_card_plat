'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money } from '@/lib/format';

import { CardThumb } from './CardThumb';

type Listing = {
  item_id: string;
  title: string;
  price: number;
  shipping?: number | null;
  url: string;
  image?: string | null;
  buying_options?: string[];
  bid_count?: number | null;
  ends_at?: string | null;
  date?: string | null;
  grade: string;
  exact_match: boolean;
  mismatches: string[];
};
type Stats = { count: number; low: number; median: number; high: number } | null;
type Market = {
  query: string;
  active: Listing[];
  active_stats: Stats;
  sold: Listing[] | null;
  sold_stats: Stats;
  insights_available: boolean;
  total_found: number | null;
};

export function EbayMarketPanel({ cardId, grade, query, player }: { cardId?: number; grade?: string; query?: string; player?: string | null }) {
  const router = useRouter();
  const [data, setData] = useState<Market | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [off, setOff] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showSimilar, setShowSimilar] = useState(!cardId);
  const [busy, setBusy] = useState<string | null>(null);
  const [saved, setSaved] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const qs = cardId ? `card_id=${cardId}${grade ? `&grade=${grade}` : ''}` : `q=${encodeURIComponent(query ?? '')}`;
    setLoading(true);
    setErr(null);
    api<Market>(`/market/ebay/listings?${qs}`)
      .then(setData)
      .catch((e: Error) => (e.message.includes('eBay is off') ? setOff(true) : setErr(e.message)))
      .finally(() => setLoading(false));
  }, [cardId, grade, query]);

  async function setCardPhoto(url: string) {
    if (!cardId) return;
    setBusy(url);
    try {
      await api(`/catalog/cards/${cardId}/image`, { method: 'PUT', body: JSON.stringify({ image_url: url }) });
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function saveSold(s: Listing) {
    if (!cardId || !s.date) return;
    setBusy(s.item_id);
    try {
      await api('/market/ebay/save-sold', {
        method: 'POST',
        body: JSON.stringify({ card_id: cardId, item_id: s.item_id, title: s.title, url: s.url, price: s.price, date: s.date, grade: s.grade }),
      });
      setSaved((x) => ({ ...x, [s.item_id]: true }));
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (off) {
    return (
      <section className="panel p-5" aria-label="eBay market">
        <h2 className="panel-title">eBay market</h2>
        <p className="mt-1 text-[13px] text-muted">
          Off. Add <code className="font-mono text-ink">EBAY_CLIENT_ID</code> and <code className="font-mono text-ink">EBAY_CLIENT_SECRET</code> to{' '}
          <code className="font-mono text-ink">.env</code> and restart.
        </p>
      </section>
    );
  }

  const active = (data?.active ?? []).filter((a) => showSimilar || a.exact_match);
  const hidden = (data?.active.length ?? 0) - active.length;

  return (
    <section className="panel" aria-label="eBay market">
      <div className="panel-head flex-wrap">
        <div>
          <h2 className="panel-title">eBay market</h2>
          <p className="text-[12px] text-muted">
            Live from the eBay API{data ? ` · searched “${data.query}”` : ''}
            {data?.total_found ? ` · ${data.total_found} results` : ''}
          </p>
        </div>
        {cardId && data && (
          <label className="flex min-h-11 items-center gap-2 text-[13px]">
            <input type="checkbox" className="h-4 w-4 accent-up" checked={showSimilar} onChange={(e) => setShowSimilar(e.target.checked)} />
            Show similar listings
          </label>
        )}
      </div>

      <div className="space-y-4 p-5">
        {loading && <p className="text-[13px] text-muted">Loading eBay listings…</p>}
        {err && <p className="text-[13px] text-down">{err}</p>}

        {data && (
          <>
            <div className="grid grid-cols-2 gap-2 font-mono text-[12px] sm:grid-cols-4">
              <Tile label={cardId ? 'Exact listings' : 'Listings'} value={String(data.active_stats?.count ?? 0)} />
              <Tile label="Lowest ask" value={money(data.active_stats?.low)} accent />
              <Tile label="Median ask" value={money(data.active_stats?.median)} />
              <Tile
                label={data.insights_available ? 'Median sold (90d)' : 'Sold data'}
                value={data.insights_available ? money(data.sold_stats?.median) : 'no access'}
              />
            </div>
            {!data.insights_available && (
              <p className="text-[12px] text-muted">
                Your eBay keyset can read live listings but not sold history (that needs eBay’s Marketplace Insights approval). Asking prices are
                shown for reference and are not used in your valuation.
              </p>
            )}

            {data.sold && data.sold.length > 0 && (
              <div>
                <p className="eyebrow mb-2">Sold on eBay ({data.sold.length})</p>
                <ul className="divide-y divide-line rounded-md border border-line">
                  {data.sold.map((s) => (
                    <Row key={s.item_id} it={s} player={player}>
                      {cardId && s.exact_match && s.date ? (
                        saved[s.item_id] ? (
                          <span className="text-[12px] text-up">Saved</span>
                        ) : (
                          <button className="btn-ghost min-h-9 px-3 text-[12px]" disabled={busy === s.item_id} onClick={() => saveSold(s)}>
                            Save as comp
                          </button>
                        )
                      ) : null}
                    </Row>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <p className="eyebrow mb-2">
                Listed now ({active.length}){hidden > 0 ? ` · ${hidden} similar hidden` : ''}
              </p>
              {active.length === 0 ? (
                <p className="text-[13px] text-muted">{hidden > 0 ? 'No exact matches listed right now — tick “Show similar listings”.' : 'Nothing listed right now.'}</p>
              ) : (
                <ul className="divide-y divide-line rounded-md border border-line">
                  {active.slice(0, 25).map((a) => (
                    <Row key={a.item_id} it={a} player={player}>
                      {cardId && a.image && a.exact_match && (
                        <button className="btn-ghost min-h-9 px-3 text-[12px]" disabled={busy === a.image} onClick={() => setCardPhoto(a.image!)}>
                          Use photo
                        </button>
                      )}
                    </Row>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="tile">
      <span className="text-muted">{label}</span>
      <br />
      <b className={`text-[16px] ${accent ? 'text-up' : ''}`}>{value}</b>
    </div>
  );
}

function Row({ it, player, children }: { it: Listing; player?: string | null; children?: React.ReactNode }) {
  const auction = it.buying_options?.includes('AUCTION');
  return (
    <li className="flex items-center gap-3 px-3 py-2.5">
      <CardThumb src={it.image ?? null} player={player ?? null} alt={it.title} />
      <div className="min-w-0 flex-1">
        <a href={it.url} target="_blank" rel="noopener noreferrer nofollow" className="block truncate text-[13px] text-ink hover:text-link" title={it.title}>
          {it.title}
        </a>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted">
          {it.exact_match ? (
            <span className="badge bg-up/15 text-up">exact</span>
          ) : (
            <span className="badge bg-warn/15 text-warn">differs: {it.mismatches.join(', ') || 'unknown'}</span>
          )}
          <span className="font-mono">{it.grade}</span>
          {it.date && <span>sold {longDate(it.date)}</span>}
          {auction && <span>auction{it.bid_count ? ` · ${it.bid_count} bids` : ''}</span>}
          {!auction && it.buying_options?.includes('BEST_OFFER') && <span>best offer</span>}
        </p>
      </div>
      <div className="text-right font-mono">
        <b className="text-[14px]">{money(it.price)}</b>
        {it.shipping !== undefined && it.shipping !== null && <span className="block text-[11px] text-muted">+{money(it.shipping)} ship</span>}
      </div>
      <div className="w-[96px] text-right">{children}</div>
    </li>
  );
}
