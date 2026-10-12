'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/client-api';
import { money } from '@/lib/format';

type Listing = { item_id: string; title: string; price: number; image?: string | null; exact_match: boolean; mismatches: string[]; url: string };

/** Grid of photos from this card's live eBay listings; click one to use it. */
export function EbayPhotoPicker({
  cardId,
  query,
  grade,
  onPick,
  onClose,
}: {
  cardId?: number | null;
  query?: string;
  grade?: string;
  onPick: (imageUrl: string) => void;
  onClose: () => void;
}) {
  const [items, setItems] = useState<Listing[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [similar, setSimilar] = useState(false);

  useEffect(() => {
    const qs = cardId ? `card_id=${cardId}${grade ? `&grade=${grade}` : ''}` : `q=${encodeURIComponent(query ?? '')}`;
    api<{ active: Listing[] }>(`/market/ebay/listings?${qs}`)
      .then((d) => setItems(d.active.filter((a) => a.image)))
      .catch((e: Error) => setErr(e.message));
  }, [cardId, query, grade]);

  const exact = (items ?? []).filter((i) => i.exact_match);
  const shown = similar || exact.length === 0 ? items ?? [] : exact;

  return (
    <div className="space-y-3 rounded-md border border-edge bg-base p-3" role="dialog" aria-label="Pick a photo from eBay">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] font-bold">Pick a photo from live eBay listings</p>
        <div className="flex items-center gap-3">
          {exact.length > 0 && exact.length < (items?.length ?? 0) && (
            <label className="flex min-h-11 items-center gap-2 text-[12px]">
              <input type="checkbox" className="h-4 w-4 accent-up" checked={similar} onChange={(e) => setSimilar(e.target.checked)} />
              Include similar
            </label>
          )}
          <button type="button" className="btn-ghost px-3 text-[12px]" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      {err && <p className="text-[12px] text-down">{err}</p>}
      {!items && !err && <p className="text-[12px] text-muted">Loading eBay photos…</p>}
      {items && items.length === 0 && <p className="text-[12px] text-muted">No listings with photos found on eBay right now.</p>}
      {items && exact.length === 0 && items.length > 0 && (
        <p className="text-[12px] text-warn">No exact matches listed — these are similar cards. Check the parallel and number before picking.</p>
      )}
      {shown.length > 0 && (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-3">
          {shown.slice(0, 24).map((it) => (
            <li key={it.item_id}>
              <button
                type="button"
                onClick={() => onPick(it.image!)}
                className="group flex w-full flex-col gap-1 rounded-md p-1 text-left hover:bg-raised focus-visible:bg-raised"
                title={it.title}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- remote eBay images */}
                <img
                  src={it.image!}
                  alt={it.title}
                  loading="lazy"
                  className="aspect-[5/7] w-full rounded-[4px] border border-edge object-cover group-hover:border-up"
                />
                <span className="flex items-center justify-between gap-1 font-mono text-[11px]">
                  <span className={it.exact_match ? 'text-up' : 'text-warn'}>{it.exact_match ? 'exact' : 'similar'}</span>
                  <span className="text-muted">{money(it.price, { whole: true })}</span>
                </span>
                <span className="line-clamp-2 text-[11px] leading-snug text-muted">{it.title}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-muted">Photos belong to eBay sellers; they’re shown here for your own reference.</p>
    </div>
  );
}
