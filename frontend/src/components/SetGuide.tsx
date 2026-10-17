'use client';

import { useEffect, useMemo, useState } from 'react';

import { api } from '@/lib/client-api';
import { money } from '@/lib/format';
import {
  baseParallel,
  boxOdds,
  fmtBoxes,
  fmtPacks,
  fmtPct,
  type BoxType,
  type PriceResult,
  type SetCard,
  type SetInsert,
  type SetParallel,
  type SetProduct,
} from '@/lib/sets';

import { CardPhoto } from './SetCardImage';
import { SetImportForm } from './SetImportForm';
import { SetPricePanel } from './SetPricePanel';

type Sort = 'checklist' | 'price' | 'player';
type PhotoResult = { source: 'ebay' | 'compsapi' | null; searched: number; added: number; missing: number; skipped: boolean };

function median(xs: number[]) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Median of the per-card medians we've already looked up for one parallel of an insert. */
function insertPrice(ins: SetInsert, par: SetParallel | undefined) {
  if (!par) return { median: null, priced: 0 };
  const ms = ins.cards.map((c) => c.prices[String(par.id)]?.median).filter((x): x is number => typeof x === 'number');
  return { median: median(ms), priced: ms.length };
}

function setUrl(box: string, insert: number | null) {
  const p = new URLSearchParams(window.location.search);
  p.set('box', box);
  if (insert) p.set('insert', String(insert));
  else p.delete('insert');
  window.history.replaceState(null, '', `${window.location.pathname}?${p}`);
}

export function SetGuide({ initial, initialBox, initialInsert }: { initial: SetProduct; initialBox?: string; initialInsert?: number }) {
  const [product, setProduct] = useState(initial);
  const boxes = product.box_types;
  const [boxName, setBoxName] = useState(boxes.find((b) => b.name === initialBox)?.name ?? boxes.find((b) => b.name === 'Mega')?.name ?? boxes[0]?.name ?? '');
  const box = boxes.find((b) => b.name === boxName) ?? boxes[0];
  const [insertId, setInsertId] = useState<number | null>(initialInsert ?? null);

  const rows = useMemo(() => {
    const list = product.inserts.map((ins) => {
      const base = baseParallel(ins);
      const odds = box ? boxOdds(base?.odds[box.name], box) : null;
      return { ins, base, odds, price: insertPrice(ins, base) };
    });
    // Most likely pull first; inserts that aren't in this box go last.
    return list.sort((a, b) => (b.odds ? 1 / b.odds.packs : -1) - (a.odds ? 1 / a.odds.packs : -1));
  }, [product, box]);

  const selected = product.inserts.find((i) => i.id === insertId) ?? null;

  function pickBox(name: string) {
    setBoxName(name);
    setUrl(name, insertId);
  }
  function pickInsert(id: number) {
    setInsertId(id);
    setUrl(boxName, id);
    setTimeout(() => document.getElementById('insert-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 30);
  }

  function onPriced(cardId: number, parId: number, r: PriceResult) {
    setProduct((p) => ({
      ...p,
      inserts: p.inserts.map((ins) => ({
        ...ins,
        cards: ins.cards.map((c) =>
          c.id !== cardId
            ? c
            : {
                ...c,
                image_url: c.image_url ?? r.items.find((x) => x.image)?.image ?? null,
                prices: {
                  ...c.prices,
                  [String(parId)]: {
                    count: r.count,
                    median: r.stats?.median ?? null,
                    last: r.last_sale?.total ?? null,
                    last_date: r.last_sale?.date ?? null,
                    fetched_at: r.fetched_at,
                  },
                },
              },
        ),
      })),
    }));
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">
            {product.sport} · Insert &amp; SSP guide
          </p>
          <h1 className="text-[22px] font-bold">{product.name}</h1>
          {product.source_note && <p className="mt-1 max-w-3xl text-[12px] text-muted">{product.source_note}</p>}
        </div>
        <SetImportForm product={product} />
      </div>

      <BoxTabs product={product} box={box} onPick={pickBox} onEdited={(b) => setProduct((p) => ({ ...p, box_types: p.box_types.map((x) => (x.id === b.id ? b : x)) }))} />

      {box && (
        <section className="panel overflow-hidden" aria-label={`Inserts in a ${box.name} box`}>
          <div className="panel-head">
            <h2 className="panel-title">What can come out of a {box.name} box</h2>
            <span className="text-[12px] text-muted">Click an insert to see its cards</span>
          </div>
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[760px] text-[13px]">
              <thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Insert</th>
                  <th className="px-2 py-2 text-right font-medium">Cards</th>
                  <th className="px-2 py-2 text-right font-medium">Pack odds</th>
                  <th className="px-2 py-2 text-right font-medium">Per box</th>
                  <th className="px-2 py-2 text-right font-medium">How often</th>
                  <th className="px-2 py-2 text-right font-medium" title="Average number per sealed case">Per case</th>
                  <th className="px-4 py-2 text-right font-medium">Median sold</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ ins, odds, price }) => (
                  <tr
                    key={ins.id}
                    onClick={() => pickInsert(ins.id)}
                    className={`cursor-pointer border-t border-line hover:bg-raised ${insertId === ins.id ? 'bg-raised' : ''} ${odds ? '' : 'text-muted'}`}
                  >
                    <td className="px-4 py-2.5">
                      <button type="button" className="text-left font-bold text-ink hover:text-link" onClick={(e) => {
                          e.stopPropagation();
                          pickInsert(ins.id);
                        }}>
                        {ins.name}
                      </button>
                      {ins.code && <span className="ml-2 font-mono text-[11px] text-muted">{ins.code}</span>}
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono">{ins.cards.length || '—'}</td>
                    {odds ? (
                      <>
                        <td className="px-2 py-2.5 text-right font-mono">{fmtPacks(odds.packs)}</td>
                        <td className="px-2 py-2.5 text-right font-mono font-bold">{fmtPct(odds.perBox)}</td>
                        <td className="px-2 py-2.5 text-right font-mono">{fmtBoxes(odds.boxesPerHit)}</td>
                        <td className="px-2 py-2.5 text-right font-mono">{odds.perCase === null ? '—' : odds.perCase < 0.01 ? '<0.01' : odds.perCase.toFixed(odds.perCase < 1 ? 2 : 1)}</td>
                      </>
                    ) : (
                      <td colSpan={4} className="px-2 py-2.5 text-right text-[12px]">
                        Not in {box.name} boxes
                      </td>
                    )}
                    <td className="px-4 py-2.5 text-right font-mono">
                      {price.median !== null ? (
                        <>
                          {money(price.median)} <span className="text-[11px] text-muted">({price.priced} priced)</span>
                        </>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line px-4 py-2 text-[11px] text-muted">
            Odds are Topps’ published pack odds for the base version of each insert. “Per box” is the chance of at least one in a {box.packs_per_box ?? '?'}-pack box; real boxes vary.
          </p>
        </section>
      )}

      {selected && box && (
        <InsertDetail
          key={selected.id}
          product={product}
          ins={selected}
          box={box}
          onPriced={onPriced}
          onReload={async () => setProduct(await api<SetProduct>(`/sets/${product.id}`))}
        />
      )}
    </div>
  );
}

function BoxTabs({ product, box, onPick, onEdited }: { product: SetProduct; box: BoxType | undefined; onPick: (n: string) => void; onEdited: (b: BoxType) => void }) {
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!box) return;
    const f = new FormData(e.currentTarget);
    const packs = Number(f.get('packs'));
    const perCase = Number(f.get('case'));
    try {
      await api(`/sets/${product.id}/box-types/${box.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ packs_per_box: packs || null, boxes_per_case: perCase || null }),
      });
      onEdited({ ...box, packs_per_box: packs || box.packs_per_box, boxes_per_case: perCase || box.boxes_per_case });
      setEditing(false);
      setErr(null);
    } catch (e2) {
      setErr((e2 as Error).message);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div role="tablist" aria-label="Box type" className="flex flex-wrap gap-1 rounded-md border border-edge p-1">
        {product.box_types.map((b) => (
          <button
            key={b.id}
            role="tab"
            aria-selected={box?.id === b.id}
            onClick={() => onPick(b.name)}
            className={`min-h-11 rounded px-4 text-left ${box?.id === b.id ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
          >
            <span className="block text-[14px] font-bold">{b.name}</span>
            <span className="block font-mono text-[11px]">
              {b.packs_per_box ?? '?'} packs{b.cards_per_pack ? ` × ${b.cards_per_pack}` : ''}
            </span>
          </button>
        ))}
      </div>
      {box &&
        (editing ? (
          <form onSubmit={save} className="flex flex-wrap items-center gap-2 text-[12px]">
            <label className="flex items-center gap-1 text-muted">
              Packs per {box.name} box
              <input name="packs" type="number" min={1} max={1000} defaultValue={box.packs_per_box ?? ''} className="field h-9 w-20" />
            </label>
            <label className="flex items-center gap-1 text-muted">
              Boxes per case
              <input name="case" type="number" min={1} max={1000} defaultValue={box.boxes_per_case ?? ''} className="field h-9 w-20" />
            </label>
            <button className="btn-primary h-9 min-h-0">Save</button>
            <button type="button" className="btn-ghost h-9 min-h-0" onClick={() => setEditing(false)}>
              Cancel
            </button>
            {err && <span className="text-down">{err}</span>}
          </form>
        ) : (
          <button type="button" className="text-[12px] text-link hover:text-ink" onClick={() => setEditing(true)}>
            Your {box.name} box has a different pack count?
          </button>
        ))}
    </div>
  );
}

function InsertDetail({
  product,
  ins,
  box,
  onPriced,
  onReload,
}: {
  product: SetProduct;
  ins: SetInsert;
  box: BoxType;
  onPriced: (cardId: number, parId: number, r: PriceResult) => void;
  onReload: () => Promise<void>;
}) {
  const missing = ins.cards.filter((c) => !c.image_url).length;
  const [photoMsg, setPhotoMsg] = useState<string | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);

  function findPhotos(force: boolean) {
    setPhotoBusy(true);
    setPhotoMsg('Finding card photos…');
    api<PhotoResult>(`/sets/inserts/${ins.id}/photos${force ? '?force=true' : ''}`, { method: 'POST' })
      .then(async (r) => {
        await onReload();
        if (r.skipped) return setPhotoMsg(null);
        const from = r.source === 'ebay' ? 'eBay listings (free)' : '1 CompsAPI search';
        setPhotoMsg(
          `Found ${r.added} photo${r.added === 1 ? '' : 's'} from ${from}.` +
            (r.missing ? ` ${r.missing} card${r.missing === 1 ? '' : 's'} had no listing — they get a photo when you check their price.` : ''),
        );
      })
      .catch((e: Error) => setPhotoMsg(e.message.includes('compsapi_off') ? 'Photos need a CompsAPI key in .env.' : `Photo search failed: ${e.message}`))
      .finally(() => setPhotoBusy(false));
  }

  // First time an insert is opened: one search fills in photos for every card it can.
  useEffect(() => {
    if (missing && !ins.photos_checked_at) findPhotos(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per insert
  }, [ins.id]);

  const [parId, setParId] = useState(baseParallel(ins)?.id ?? 0);
  const par = ins.parallels.find((p) => p.id === parId) ?? ins.parallels[0];
  const [sort, setSort] = useState<Sort>('checklist');
  const [rcOnly, setRcOnly] = useState(false);
  const [open, setOpen] = useState<SetCard | null>(null);

  const odds = par ? boxOdds(par.odds[box.name], box) : null;
  const n = ins.cards.length;
  const price = insertPrice(ins, par);
  const owned = ins.cards.filter((c) => c.owned > 0).length;

  const cards = useMemo(() => {
    let list = rcOnly ? ins.cards.filter((c) => c.rookie) : ins.cards;
    if (sort === 'player') list = [...list].sort((a, b) => a.player.localeCompare(b.player));
    if (sort === 'price') {
      const key = String(par?.id);
      list = [...list].sort((a, b) => (b.prices[key]?.median ?? -1) - (a.prices[key]?.median ?? -1));
    }
    return list;
  }, [ins.cards, rcOnly, sort, par]);

  return (
    <section id="insert-detail" className="panel scroll-mt-4" aria-label={`${ins.name} checklist`}>
      <div className="panel-head flex-wrap">
        <div>
          <h2 className="text-[18px] font-bold">
            {ins.name} {ins.code && <span className="font-mono text-[12px] font-normal text-muted">{ins.code}</span>}
          </h2>
          <p className="text-[12px] text-muted">
            {n} cards{owned ? ` · you have ${owned}` : ''}
            {price.priced ? ` · ${price.priced} priced` : ''}
          </p>
        </div>
      </div>

      <div className="space-y-4 p-4 sm:p-5">
        <div role="tablist" aria-label="Parallel" className="flex flex-wrap gap-2">
          {ins.parallels.map((p) => {
            const o = p.odds[box.name];
            return (
              <button
                key={p.id}
                role="tab"
                aria-selected={p.id === par?.id}
                onClick={() => setParId(p.id)}
                className={`min-h-11 rounded-md border px-3 text-left ${p.id === par?.id ? 'border-up/60 bg-up/10 text-ink' : 'border-edge text-muted hover:text-ink'}`}
              >
                <span className="block text-[13px] font-bold">
                  {p.name === 'Base' ? 'Base' : p.name}
                  {p.print_run ? <span className="font-mono font-normal"> {p.print_run === 1 ? '1/1' : `/${p.print_run}`}</span> : null}
                </span>
                <span className="block font-mono text-[11px]">{o ? `${fmtPacks(o)} packs` : 'odds not published'}</span>
              </button>
            );
          })}
        </div>

        <div className="grid gap-2 font-mono text-[12px] sm:grid-cols-4">
          <div className="tile">
            <span className="text-muted">Any {ins.name}{par && par.name !== 'Base' ? ` ${par.name}` : ''} per {box.name}</span>
            <br />
            <b className="text-[16px]">{odds ? fmtPct(odds.perBox) : par?.odds && Object.keys(par.odds).length ? `not in ${box.name}` : '—'}</b>
            {odds?.boxesPerHit ? <span className="block text-[11px] text-muted">{fmtBoxes(odds.boxesPerHit)}</span> : null}
          </div>
          <div className="tile">
            <span className="text-muted">One specific card</span>
            <br />
            <b className="text-[16px]">{odds && n ? fmtBoxes(odds.boxesPerHit !== null ? odds.boxesPerHit * n : null) : '—'}</b>
            {odds && n ? <span className="block text-[11px] text-muted">{fmtPacks(odds.packs * n)} packs, if all {n} fall evenly</span> : null}
          </div>
          <div className="tile">
            <span className="text-muted">Median sold (priced cards)</span>
            <br />
            <b className="text-[16px]">{money(price.median)}</b>
            <span className="block text-[11px] text-muted">{price.priced} of {n} looked up</span>
          </div>
          <div className="tile">
            <span className="text-muted">Worth per {box.name} box (rough)</span>
            <br />
            <b className="text-[16px]">{odds?.perBox != null && price.median !== null && price.priced >= 3 ? money(odds.perBox * price.median) : '—'}</b>
            <span className="block text-[11px] text-muted">{price.priced >= 3 ? 'chance per box × median' : 'price 3+ cards to estimate'}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-[12px] text-muted">
            Sort
            <select className="field h-10 w-auto py-0 text-[13px]" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="checklist">Checklist order</option>
              <option value="price">Median sold</option>
              <option value="player">Player A–Z</option>
            </select>
          </label>
          <button
            type="button"
            aria-pressed={rcOnly}
            onClick={() => setRcOnly(!rcOnly)}
            className={`h-10 rounded-md border border-edge px-3 text-[12px] ${rcOnly ? 'bg-warn/15 text-warn' : 'text-muted hover:text-ink'}`}
          >
            RC only
          </button>
          <span className="text-[12px] text-muted">Click a card to look up its sold prices.</span>
        </div>
        <p className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
          {photoMsg ?? (missing > 0 && ins.photos_checked_at ? `${missing} card${missing === 1 ? '' : 's'} without a photo.` : null)}
          {ins.photos_checked_at && !photoBusy && (
            <button type="button" className="text-link hover:text-ink" onClick={() => findPhotos(true)} title="Look up photos again for every card you haven't picked a photo for">
              Re-pick photos (1 search)
            </button>
          )}
          <span>Wrong photo? Open the card and choose one of its sales’ photos.</span>
        </p>

        {n === 0 ? (
          <p className="text-[13px] text-muted">{ins.note ?? 'No checklist yet.'}</p>
        ) : (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
            {cards.map((c) => {
              const pr = par ? c.prices[String(par.id)] : undefined;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setOpen(c)}
                    className="panel flex h-full w-full flex-col overflow-hidden text-left hover:border-up/50"
                    aria-label={`${c.number} ${c.player}: look up sold prices`}
                  >
                    <div className="relative w-full bg-base">
                      <TileImage card={c} />
                      <div className="absolute left-1.5 top-1.5 flex gap-1">
                        {c.rookie && <span className="badge bg-warn/20 text-warn">RC</span>}
                        {c.owned > 0 && <span className="badge bg-up/20 text-up">✓ Have{c.owned > 1 ? ` ×${c.owned}` : ''}</span>}
                      </div>
                    </div>
                    <div className="flex flex-1 flex-col gap-0.5 p-2.5">
                      <span className="font-mono text-[11px] text-muted">{c.number}</span>
                      <span className="line-clamp-1 text-[13px] font-bold">{c.player}</span>
                      <span className="line-clamp-1 text-[11px] text-muted">{c.team}</span>
                      <span className="mt-auto pt-1 font-mono text-[13px]">
                        {pr ? (
                          pr.median !== null ? (
                            <>
                              <b>{money(pr.median)}</b> <span className="text-[11px] text-muted">median · {pr.count}</span>
                            </>
                          ) : (
                            <span className="text-[11px] text-muted">no sales found</span>
                          )
                        ) : (
                          <span className="text-[12px] text-link">Check price →</span>
                        )}
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {open && par && (
        <SetPricePanel
          product={product}
          ins={ins}
          card={open}
          parallel={par}
          onParallel={setParId}
          onResult={(r, pid) => onPriced(open.id, pid, r)}
          onPhotoChanged={onReload}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  );
}

/** Card photo, or the number and name when there's none (or it fails to load). */
function TileImage({ card }: { card: SetCard }) {
  return (
    <CardPhoto
      src={card.image_url}
      crop={card.image_crop}
      fallback={
        <div className="flex aspect-[5/7] flex-col items-center justify-center gap-1 p-2 text-center">
          <span className="font-mono text-[12px] text-muted">{card.number}</span>
          <span className="text-[13px] font-bold text-ink">{card.player}</span>
          <span className="text-[11px] text-muted">{card.image_url ? 'photo unavailable' : 'no photo yet'}</span>
        </div>
      }
    />
  );
}
