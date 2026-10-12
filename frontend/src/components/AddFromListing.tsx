'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { api } from '@/lib/client-api';
import { resizeForUpload } from '@/lib/images';
import { money } from '@/lib/format';
import type { Holding } from '@/lib/types';

import type { SearchListing } from './EbaySearch';
import { SalesGrid, emptyRow, saveSales, validRows, type SaleRow } from './SalesGrid';

type CardFields = {
  sport: string | null;
  year: number | null;
  brand: string | null;
  set_name: string | null;
  player: string | null;
  card_number: string | null;
  parallel: string | null;
  print_run: number | null;
  rookie: boolean;
  autograph: boolean;
  grader: string | null;
  grade_value: string | null;
};
type Item = { item_id: string; title: string; price: number | null; url: string; image: string | null; card: CardFields };

const GRADES = ['raw', '10', '9.5', '9', '8.5', '8', '7', '6', '5', '4', '3', '2', '1'];
const GRADERS = ['PSA', 'BGS', 'SGC', 'CGC'];
const SPORTS = ['Baseball', 'Basketball', 'Football', 'Hockey', 'Soccer', 'Other'];

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/** Dialog: confirm the card details eBay gave us, enter what you paid, add to collection. */
export function AddFromListing({ listing, onClose }: { listing: SearchListing; onClose: () => void }) {
  const [item, setItem] = useState<Item | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Holding | null>(null);
  const [photoMode, setPhotoMode] = useState<'listing' | 'own' | 'none'>('listing');
  const [own, setOwn] = useState<{ content_type: string; data_base64: string; preview: string } | null>(null);
  const [ownUrl, setOwnUrl] = useState('');
  const [sales, setSales] = useState<SaleRow[]>([emptyRow()]);
  const [salesResult, setSalesResult] = useState<{ saved: number; errors: string[] } | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api<Item>(`/market/ebay/item/${encodeURIComponent(listing.item_id)}`)
      .then(setItem)
      .catch((e: Error) => setErr(e.message));
    ref.current?.focus();
  }, [listing.item_id]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const grade = String(f.get('grade'));
    setBusy(true);
    setErr(null);
    try {
      const h = await api<Holding>('/collection/items/quick-add', {
        method: 'POST',
        body: JSON.stringify({
          card: {
            sport: f.get('sport'),
            year: Number(f.get('year')),
            brand: f.get('brand'),
            set_name: f.get('set_name'),
            player: f.get('player'),
            card_number: f.get('card_number'),
            parallel: f.get('parallel') || 'Base',
            print_run: f.get('print_run') ? Number(f.get('print_run')) : null,
            rookie: f.get('rookie') === 'on',
            autograph: f.get('autograph') === 'on',
          },
          grader: grade === 'raw' ? null : f.get('grader'),
          grade_value: grade === 'raw' ? null : grade,
          purchase_price: Number(f.get('purchase_price')),
          purchase_date: f.get('purchase_date'),
          quantity: Number(f.get('quantity')),
          notes: f.get('notes') || null,
          image_url:
            photoMode === 'listing' ? item?.image ?? listing.image : photoMode === 'own' && !own && ownUrl.trim() ? ownUrl.trim() : null,
        }),
      });
      let saved = h;
      if (photoMode === 'own' && own) {
        saved = await api<Holding>(`/collection/items/${h.id}/photo`, {
          method: 'PUT',
          body: JSON.stringify({ content_type: own.content_type, data_base64: own.data_base64 }),
        });
      }
      // sales typed/pasted in this dialog
      if (validRows(sales).length) {
        setSalesResult(await saveSales(h.card_id, sales));
        saved = await api<Holding>(`/collection/items/${h.id}`);
      } else {
        // nothing entered: try to find sold data in the background
        const g = h.grade_value ? `psa${h.grade_value}` : 'raw';
        api(`/market/sync/${h.card_id}?grade=${g}`, { method: 'POST' }).catch(() => {});
      }
      setDone(saved);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const c = item?.card;
  const field = (name: keyof CardFields | 'print_run', label: string, value: unknown, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <label htmlFor={`afl-${name}`} className="eyebrow">
        {label}
      </label>
      <input id={`afl-${name}`} name={name} defaultValue={(value as string | number | null) ?? ''} className="field" {...extra} />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-8" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Add to collection"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        className="panel w-full max-w-5xl outline-none"
      >
        <div className="panel-head">
          <h2 className="panel-title">Add to collection</h2>
          <button className="btn-ghost px-3" onClick={onClose}>
            Close
          </button>
        </div>

        {done ? (
          <div className="space-y-4 p-5">
            <p className="font-bold text-up">Added: {done.title}</p>
            {salesResult ? (
              <p className="text-[13px] text-muted">
                Saved {salesResult.saved} sale{salesResult.saved === 1 ? '' : 's'}
                {done.median_30d !== null ? ` · 30-day median ${money(done.median_30d)} · last sale ${money(done.last_sale_price)}` : ''}.
                {salesResult.errors.length > 0 && <span className="block text-down">Not saved: {salesResult.errors.join(' · ')}</span>}
              </p>
            ) : (
              <p className="text-[13px] text-muted">No sales entered — looking for recent sales in the background. You can add them later on the card page.</p>
            )}
            <div className="flex flex-wrap gap-2">
              <Link href={`/cards/${done.card_id}?grade=${done.grade_value ? `psa${done.grade_value}` : 'raw'}`} className="btn-primary text-[#06281A] hover:text-[#06281A]">
                Open card page
              </Link>
              <Link href="/collection" className="btn-ghost">
                Go to collection
              </Link>
              <button className="btn-ghost" onClick={onClose}>
                Keep searching
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-5 p-5">
            <div className="w-[160px] shrink-0 space-y-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- remote eBay image */}
              {(item?.image ?? listing.image) && <img src={(item?.image ?? listing.image)!} alt={listing.title} className="aspect-[5/7] w-full rounded-md border border-edge object-contain" />}
              <a href={listing.url} target="_blank" rel="noopener noreferrer nofollow" className="block text-[12px] text-link hover:text-ink">
                View listing ↗
              </a>
              <p className="text-[11px] leading-snug text-muted">{listing.title}</p>
            </div>

            {!item && !err && <p className="text-[13px] text-muted">Reading card details from eBay…</p>}
            {err && !item && <p className="text-[13px] text-down">{err}</p>}

            {c && (
              <form onSubmit={submit} className="min-w-[280px] flex-1 space-y-4">
                <p className="text-[12px] text-muted">Filled from the seller’s item specifics — check them; sellers sometimes get these wrong.</p>
                <div className="grid grid-cols-2 gap-3">
                  {field('player', 'Player', c.player, { required: true })}
                  {field('year', 'Year', c.year, { type: 'number', required: true, min: 1880, max: 2100 })}
                  {field('brand', 'Brand', c.brand, { required: true })}
                  {field('set_name', 'Set', c.set_name, { required: true })}
                  {field('card_number', 'Card #', c.card_number, { required: true })}
                  {field('parallel', 'Parallel', c.parallel ?? 'Base')}
                  {field('print_run', 'Numbered to (/__)', c.print_run, { type: 'number', min: 1 })}
                  <div className="space-y-1">
                    <label htmlFor="afl-sport" className="eyebrow">
                      Sport
                    </label>
                    <select id="afl-sport" name="sport" className="field" defaultValue={c.sport && SPORTS.includes(c.sport) ? c.sport : 'Basketball'}>
                      {SPORTS.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex flex-wrap gap-5 text-[13px]">
                  <label className="flex min-h-11 items-center gap-2">
                    <input type="checkbox" name="rookie" defaultChecked={c.rookie} className="h-4 w-4 accent-up" /> Rookie
                  </label>
                  <label className="flex min-h-11 items-center gap-2">
                    <input type="checkbox" name="autograph" defaultChecked={c.autograph} className="h-4 w-4 accent-up" /> Auto
                  </label>
                </div>

                <fieldset className="space-y-2 rounded-md border border-line p-3">
                  <legend className="eyebrow px-1">Card photo</legend>
                  <div className="flex flex-wrap gap-4 text-[13px]">
                    {(
                      [
                        ['listing', 'This listing’s photo'],
                        ['own', 'My own photo'],
                        ['none', 'No photo'],
                      ] as const
                    ).map(([v, label]) => (
                      <label key={v} className="flex min-h-11 items-center gap-2">
                        <input type="radio" name="photo_mode" value={v} checked={photoMode === v} onChange={() => setPhotoMode(v)} className="h-4 w-4 accent-up" />
                        {label}
                      </label>
                    ))}
                  </div>
                  {photoMode === 'own' && (
                    <div className="flex flex-wrap items-center gap-3">
                      {own?.preview && (
                        // eslint-disable-next-line @next/next/no-img-element -- local preview
                        <img src={own.preview} alt="Your photo" className="h-[84px] w-[60px] rounded-[4px] border border-edge object-cover" />
                      )}
                      <label className="btn-ghost cursor-pointer">
                        {own ? 'Choose another photo' : 'Upload photo'}
                        <input
                          type="file"
                          accept="image/*"
                          className="sr-only"
                          onChange={async (e) => {
                            const file = e.target.files?.[0];
                            if (!file) return;
                            try {
                              setOwn(await resizeForUpload(file));
                            } catch {
                              setErr('Could not read that image. Try a JPG or PNG.');
                            }
                          }}
                        />
                      </label>
                      <label htmlFor="afl-ownurl" className="sr-only">
                        Image URL
                      </label>
                      <input
                        id="afl-ownurl"
                        className="field min-w-[200px] flex-1"
                        placeholder="…or paste an image URL"
                        value={ownUrl}
                        onChange={(e) => setOwnUrl(e.target.value)}
                        disabled={Boolean(own)}
                      />
                    </div>
                  )}
                </fieldset>

                <div className="border-t border-line pt-4">
                  <p className="eyebrow mb-2">Your copy</p>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                    <div className="space-y-1">
                      <label htmlFor="afl-grader" className="eyebrow">
                        Grader
                      </label>
                      <select id="afl-grader" name="grader" className="field" defaultValue={c.grader ?? 'PSA'}>
                        {GRADERS.map((g) => (
                          <option key={g}>{g}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label htmlFor="afl-grade" className="eyebrow">
                        Grade
                      </label>
                      <select id="afl-grade" name="grade" className="field" defaultValue={c.grade_value ?? 'raw'}>
                        {GRADES.map((g) => (
                          <option key={g} value={g}>
                            {g === 'raw' ? 'Raw (ungraded)' : g}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label htmlFor="afl-qty" className="eyebrow">
                        Quantity
                      </label>
                      <input id="afl-qty" name="quantity" type="number" min="1" defaultValue="1" className="field" required />
                    </div>
                    <div className="space-y-1">
                      <label htmlFor="afl-price" className="eyebrow">
                        You paid (each)
                      </label>
                      <input
                        id="afl-price"
                        name="purchase_price"
                        type="number"
                        min="0"
                        step="0.01"
                        required
                        defaultValue={item?.price ?? listing.price}
                        className="field"
                      />
                    </div>
                    <div className="space-y-1">
                      <label htmlFor="afl-date" className="eyebrow">
                        Bought on
                      </label>
                      <input id="afl-date" name="purchase_date" type="date" required defaultValue={today()} className="field" />
                    </div>
                    <div className="space-y-1">
                      <label htmlFor="afl-notes" className="eyebrow">
                        Notes
                      </label>
                      <input id="afl-notes" name="notes" className="field" placeholder="Optional" />
                    </div>
                  </div>
                  <p className="mt-2 text-[12px] text-muted">Price is pre-filled with this listing’s {money(item?.price ?? listing.price)} — change it to what you actually paid.</p>
                </div>
                <div className="border-t border-line pt-4">
                  <p className="eyebrow mb-2">Recent sales (optional)</p>
                  <SalesGrid
                    rows={sales}
                    onChange={setSales}
                    defaultGrade={c.grade_value ? `${c.grader ?? 'PSA'} ${c.grade_value}` : 'Raw'}
                    soldSearchUrl={`https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(
                      [c.year, c.set_name, c.player, c.card_number, c.parallel && c.parallel !== 'Base' ? c.parallel : ''].filter(Boolean).join(' '),
                    )}&_sacat=261328&LH_Sold=1&LH_Complete=1&_sop=13`}
                  />
                </div>
                {err && <p className="text-[13px] text-down">{err}</p>}
                <div className="flex gap-2">
                  <button className="btn-primary" disabled={busy}>
                    {busy ? 'Adding…' : validRows(sales).length ? `Add to collection + ${validRows(sales).length} sale(s)` : 'Add to collection'}
                  </button>
                  <button type="button" className="btn-ghost" onClick={onClose}>
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
