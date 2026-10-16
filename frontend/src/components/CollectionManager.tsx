'use client';

import Link from 'next/link';
import { Fragment, useEffect, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money, pct, shortDate, signedMoney, tone } from '@/lib/format';
import { DEFAULT_VIEW, applyFilters, groupItems, isFiltered, sortItems, totals, viewToQuery, type View } from '@/lib/collection-view';
import { gradeParam, graderOf } from '@/lib/grade';
import { guessCard } from '@/lib/guess-card';
import { holdingImage, resizeForUpload } from '@/lib/images';
import type { CardSearchResult, CompsApiStatus, Holding, SyncResult } from '@/lib/types';

import { CardPicker } from './CardPicker';
import { CardThumb } from './CardThumb';
import { CollectionToolbar } from './CollectionToolbar';
import { EbayPhotoPicker } from './EbayPhotoPicker';
import { SalesGrid, emptyRow, saveSales, validRows, type SaleRow } from './SalesGrid';
import { NewCardForm } from './NewCardForm';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

type Skipped = NonNullable<SyncResult['skipped']>[number] & { grade?: string; added?: boolean; busy?: boolean };
type RowSync = { busy?: boolean; note?: string; bad?: boolean; skipped?: Skipped[]; open?: boolean };

const WHY: Record<string, string> = {
  'card #': 'card # differs',
  parallel: 'other parallel',
  grade: 'other grade',
  set: 'other set',
  year: 'other year',
  player: 'other player',
  'not a single card': 'lot / break / reprint',
};

function describeSync(r: SyncResult): RowSync {
  switch (r.status) {
    case 'synced':
      if (r.added > 0) return { note: `+${r.added} new sale${r.added > 1 ? 's' : ''}` };
      if (r.matched) return { note: 'Up to date' };
      return { note: r.found ? `No exact match (${r.found} similar skipped)` : 'No sales found on eBay' };
    case 'recent':
      return { note: 'Checked in the last 24h' };
    case 'quota':
      return { note: 'Monthly quota used up', bad: true };
    case 'ebay_off':
    case 'no_sold_access':
      return { note: 'Add COMPSAPI_KEY to fetch sales', bad: true };
    case 'ai_started':
    case 'ai_running':
      return { note: 'AI is searching… open the card' };
    default:
      return { note: r.message ?? r.status };
  }
}

const GRADES = ['raw', '10', '9.5', '9', '8.5', '8', '7.5', '7', '6', '5', '4', '3', '2', '1'];
const PSA_ID = 1;

type Draft = {
  card_id: number | null;
  card_title: string;
  card_parallel_id: number | null;
  grade: string;
  // Keep the holding's own grading company (BGS, SGC …); new holdings default to PSA.
  grade_company_id: number | null;
  grader: string;
  purchase_price: string;
  purchase_date: string;
  quantity: string;
  notes: string;
  image_url: string;
  current_photo: string | null; // what the thumbnail shows today
  player: string | null;
};

// Local calendar date (toISOString() is UTC, which is already "tomorrow" on US evenings).
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function blank(): Draft {
  return { card_id: null, card_title: '', card_parallel_id: null, grade: 'raw', grade_company_id: null, grader: 'PSA', purchase_price: '', purchase_date: today(), quantity: '1', notes: '', image_url: '', current_photo: null, player: null };
}

function fromHolding(h: Holding): Draft {
  return {
    card_id: h.card_id,
    card_title: h.title ?? `Card ${h.card_id}`,
    card_parallel_id: h.card_parallel_id,
    grade: h.grade_value ?? 'raw',
    grade_company_id: h.grade_company_id,
    grader: graderOf(h),
    purchase_price: String(h.purchase_price),
    purchase_date: h.purchase_date,
    quantity: String(h.quantity),
    notes: h.notes ?? '',
    image_url: h.image_url ?? '',
    current_photo: holdingImage(h),
    player: h.player,
  };
}

export function CollectionManager({
  initial,
  startAdding,
  newCardQuery,
  initialView = DEFAULT_VIEW,
}: {
  initial: Holding[];
  startAdding: boolean;
  newCardQuery?: string;
  initialView?: View;
}) {
  const [items, setItems] = useState(initial);
  const [view, setView] = useState<View>(initialView);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Keep the filters in the URL (shareable, survive refresh) without reloading the page.
  useEffect(() => {
    const keep = new URLSearchParams(window.location.search);
    const next = new URLSearchParams(viewToQuery(view).slice(1));
    for (const k of ['add', 'new']) if (keep.get(k)) next.set(k, keep.get(k)!);
    const qs = next.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
  }, [view]);
  const [editing, setEditing] = useState<number | 'new' | null>(startAdding || newCardQuery ? 'new' : null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rowSync, setRowSync] = useState<Record<number, RowSync>>({});
  const [quota, setQuota] = useState<CompsApiStatus | null>(null);
  const [bulk, setBulk] = useState<{ done: number; total: number } | null>(null);

  const refreshQuota = () =>
    api<CompsApiStatus>('/market/compsapi/status')
      .then(setQuota)
      .catch(() => setQuota(null));
  useEffect(() => {
    refreshQuota();
  }, []);

  async function reloadItems() {
    try {
      setItems(await api<Holding[]>('/collection/items'));
    } catch {
      /* keep what we have */
    }
  }

  async function syncOne(h: Holding, force: boolean): Promise<SyncResult | null> {
    setRowSync((s) => ({ ...s, [h.id]: { busy: true } }));
    try {
      const par = h.card_parallel_id ? `&parallel_id=${h.card_parallel_id}` : '';
      const r = await api<SyncResult>(`/market/sync/${h.card_id}?grade=${gradeParam(h)}${par}${force ? '&force=true' : ''}`, { method: 'POST' });
      setRowSync((s) => ({ ...s, [h.id]: { ...describeSync(r), skipped: r.skipped?.length ? r.skipped : undefined } }));
      return r;
    } catch (e) {
      setRowSync((s) => ({ ...s, [h.id]: { note: (e as Error).message, bad: true } }));
      return null;
    }
  }

  /** The row's ↻ button: always asks eBay again (spends one search). */
  async function syncRow(h: Holding) {
    const r = await syncOne(h, true);
    if (r && r.added > 0) await reloadItems();
    refreshQuota();
  }

  /** Save a sale the matcher skipped (owner says it IS this card). */
  async function addSkipped(h: Holding, k: Skipped) {
    const mark = (patch: Partial<Skipped>) =>
      setRowSync((s) => ({
        ...s,
        [h.id]: { ...s[h.id], skipped: s[h.id]?.skipped?.map((x) => (x.url === k.url ? { ...x, ...patch } : x)) },
      }));
    mark({ busy: true });
    try {
      await api(`/market/sales/${h.card_id}`, {
        method: 'POST',
        body: JSON.stringify({ price: k.total, date: k.date, grade: k.grade ?? 'Raw', url: k.url, title: k.title, source: 'eBay', card_parallel_id: h.card_parallel_id }),
      });
      mark({ busy: false, added: true });
      await reloadItems();
    } catch (e) {
      mark({ busy: false });
      // 409 = already saved for this card
      if (!(e as Error).message.toLowerCase().includes('already')) setError((e as Error).message);
      else mark({ added: true });
    }
  }

  /** Header button: every card once; cards checked in the last 24h are skipped for free. */
  async function syncAll() {
    const seen = new Set<string>();
    const todo = items.filter((h) => {
      const k = `${h.card_id}|${gradeParam(h)}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    let added = 0;
    let fetched = 0;
    setNotice(null);
    setBulk({ done: 0, total: todo.length });
    for (let i = 0; i < todo.length; i++) {
      const r = await syncOne(todo[i], false);
      added += r?.added ?? 0;
      setBulk({ done: i + 1, total: todo.length });
      if (r?.status === 'quota') break;
      if (r?.status === 'synced') {
        fetched += 1;
        if (quota?.plan === 'free' && i < todo.length - 1) await sleep(6500); // free plan: 10 searches/minute
      }
    }
    await reloadItems();
    refreshQuota();
    setBulk(null);
    setNotice(`Sales updated: ${fetched} card${fetched === 1 ? '' : 's'} checked on eBay, ${added} new sale${added === 1 ? '' : 's'} added.`);
  }

  async function remove(id: number) {
    setError(null);
    try {
      await api(`/collection/items/${id}`, { method: 'DELETE' });
      setItems((xs) => xs.filter((x) => x.id !== id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConfirmDelete(null);
    }
  }

  function saved(h: Holding, isNew: boolean) {
    setItems((xs) => (isNew ? [h, ...xs] : xs.map((x) => (x.id === h.id ? h : x))));
    setEditing(null);
    if (isNew) {
      // Pull this card's recent eBay sales right away so the row fills in.
      setNotice(`Added. Looking up recent sales for ${h.player ?? 'this card'}…`);
      syncOne(h, false).then(async (r) => {
        if (r && r.added > 0) await reloadItems();
        setNotice(r ? `Added. ${describeSync(r).note}.` : 'Added.');
        refreshQuota();
      });
    }
  }

  const all = totals(items);
  const visible = sortItems(applyFilters(items, view), view.sort);
  const shown = totals(visible);
  const filtered = isFiltered(view);
  const groups = groupItems(visible, view.group);
  const grouped = view.group !== 'none';
  const toggleGroup = (k: string) =>
    setCollapsed((c) => {
      const n = new Set(c);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold">Collection</h1>
          <p className="num mt-1 text-[13px] text-muted" aria-live="polite">
            {filtered ? `${shown.count} of ${all.count} positions` : `${all.count} positions`} · cost {money(shown.cost)} · est.{' '}
            {shown.unpriced === shown.count ? '—' : money(shown.est)} ·{' '}
            <span className={tone(shown.pnl)}>{shown.unpriced === shown.count ? '—' : signedMoney(shown.pnl)}</span>
            {shown.unpriced > 0 && <span> · {shown.unpriced} without an estimate</span>}
          </p>
        </div>
        {editing !== 'new' && (
          <div className="flex flex-wrap gap-2">
            <Link href="/search" className="btn-primary text-[#06281A] hover:text-[#06281A]">
              + Add from eBay search
            </Link>
            <button className="btn-ghost" onClick={() => setEditing('new')}>
              Add manually
            </button>
            {quota?.configured && items.length > 0 && (
              <button className="btn-ghost" onClick={syncAll} disabled={bulk !== null} aria-live="polite">
                {bulk ? `Updating ${bulk.done}/${bulk.total}…` : '↻ Update sales'}
              </button>
            )}
          </div>
        )}
      </div>

      {quota && !quota.configured && (
        <p className="text-[12px] text-muted">
          Recent sales fill in automatically once you add a free CompsAPI key: get one at{' '}
          <a href="https://app.compsapi.com" target="_blank" rel="noopener noreferrer" className="text-link">
            app.compsapi.com
          </a>
          , put <code className="font-mono">COMPSAPI_KEY=…</code> in <code className="font-mono">.env</code> and restart.
        </p>
      )}
      {quota?.configured && quota.monthly_quota != null && (
        <p className="text-[12px] text-muted">
          eBay sales via CompsAPI · {quota.monthly_used ?? 0} / {quota.monthly_quota} searches used this month ({quota.plan}). Each card is
          checked at most once a day unless you press ↻.
        </p>
      )}
      {quota?.configured && quota.error && <p className="text-[12px] text-down">CompsAPI: {quota.error}</p>}
      {editing === 'new' && <HoldingForm draft={blank()} newCardQuery={newCardQuery} onSaved={(h) => saved(h, true)} onCancel={() => setEditing(null)} />}
      {error && <p className="text-[13px] text-down">{error}</p>}
      {notice && (
        <p className="text-[13px] text-up" role="status">
          {notice}
        </p>
      )}

      {items.length > 0 && <CollectionToolbar items={items} view={view} onChange={setView} />}

      <section className="panel" aria-label="All holdings">
        {items.length === 0 ? (
          <p className="p-5 text-muted">Nothing here yet — add your first card above.</p>
        ) : visible.length === 0 ? (
          <p className="p-5 text-muted">
            No cards match these filters.{' '}
            <button className="text-link hover:text-ink" onClick={() => setView({ ...DEFAULT_VIEW, group: view.group, sort: view.sort })}>
              Clear filters
            </button>
          </p>
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[1120px] border-collapse text-[13px]">
              <thead>
                <tr>
                  <th className="th pl-5">Card</th>
                  <th className="th">Grade</th>
                  <th className="th text-right">Qty</th>
                  <th className="th text-right">Paid</th>
                  <th className="th">Bought</th>
                  <th className="th text-right">Est.</th>
                  <th className="th text-right">30d median · vol</th>
                  <th className="th text-right">Recent sales</th>
                  <th className="th text-right">Last sale</th>
                  <th className="th text-right">P&amp;L</th>
                  <th className="th pr-5 text-right">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {groups.map((g) => (
                  <Fragment key={g.key}>
                    {grouped && (
                      <tr className="border-t-2 border-line bg-raised/60 font-sans">
                        <td colSpan={3} className="px-5 py-2.5">
                          <button
                            type="button"
                            onClick={() => toggleGroup(g.key)}
                            aria-expanded={!collapsed.has(g.key)}
                            className="flex items-center gap-2 text-left text-[13px] font-bold text-ink"
                          >
                            <span className={`inline-block text-muted transition-transform ${collapsed.has(g.key) ? '-rotate-90' : ''}`}>▾</span>
                            {g.label}
                            <span className="font-mono text-[12px] font-normal text-muted">
                              {g.totals.count} card{g.totals.count === 1 ? '' : 's'}
                            </span>
                          </button>
                        </td>
                        <td className="td text-right font-mono text-[12px] text-muted" title="Total paid">
                          {money(g.totals.cost)}
                        </td>
                        <td />
                        <td className="td text-right font-mono text-[12px]" title="Total estimate">
                          {g.totals.unpriced === g.totals.count ? '—' : money(g.totals.est)}
                        </td>
                        <td colSpan={3} />
                        <td className={`td text-right font-mono text-[12px] ${tone(g.totals.pnl)}`}>
                          {g.totals.unpriced === g.totals.count ? '—' : signedMoney(g.totals.pnl)}
                        </td>
                        <td />
                      </tr>
                    )}
                {!collapsed.has(g.key) && g.items.map((h) =>
                  editing === h.id ? (
                    <tr key={h.id} className="border-t border-line">
                      <td colSpan={11} className="p-4">
                        <HoldingForm draft={fromHolding(h)} itemId={h.id} onSaved={(x) => saved(x, false)} onCancel={() => setEditing(null)} />
                      </td>
                    </tr>
                  ) : (
                    <Fragment key={h.id}>
                    <tr className="border-t border-line">
                      <td className="td pl-5 font-sans">
                        <div className="flex items-center gap-3">
                          <CardThumb src={holdingImage(h)} player={h.player} />
                          <div>
                            <Link href={`/cards/${h.card_id}?grade=${gradeParam(h)}`} className="text-ink hover:text-link">
                              <b>{h.player}</b>
                            </Link>
                            {h.rookie_flag && <span className="badge ml-1.5 bg-warn/15 text-warn">RC</span>}
                            <br />
                            <span className="text-[12px] text-muted">
                              {h.year} {h.card_set} #{h.card_number}
                              {h.parallel && h.parallel !== 'Base' ? ` · ${h.parallel}` : ''}
                            </span>
                            {h.notes && <span className="block text-[12px] italic text-muted">{h.notes}</span>}
                          </div>
                        </div>
                      </td>
                      <td className="td">{h.grade_label}</td>
                      <td className="td text-right">{h.quantity}</td>
                      <td className="td text-right">{money(h.purchase_price)}</td>
                      <td className="td text-muted">{h.purchase_date}</td>
                      <td className="td text-right">{money(h.estimated_value)}</td>
                      <td className="td text-right">
                        {h.sales_30d > 0 ? money(h.median_30d) : '—'}
                        <span className="block text-[11px] text-muted">{h.sales_30d} sold</span>
                      </td>
                      <td className="td text-right">
                        {h.recent_sales && h.recent_sales.length > 0 ? (
                          <span className="inline-flex flex-wrap justify-end gap-1" aria-label="Last sales, newest first">
                            {h.recent_sales.map((s, i) => (
                              <span key={i} title={longDate(s.date)} className="rounded bg-raised px-1.5 py-0.5 text-center leading-tight">
                                {money(s.price, { whole: s.price >= 100 })}
                                <span className="block text-[10px] text-muted">{shortDate(s.date)}</span>
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="td text-right">
                        <span className="inline-flex items-start justify-end gap-1.5">
                          <span>
                            {money(h.last_sale_price)}
                            <span className="block text-[11px] text-muted">{h.last_sale_date ? longDate(h.last_sale_date) : 'no sales yet'}</span>
                          </span>
                          {quota?.configured && (
                            <button
                              type="button"
                              onClick={() => syncRow(h)}
                              disabled={rowSync[h.id]?.busy || bulk !== null}
                              aria-label={`Fetch latest eBay sales for ${h.title}`}
                              title="Fetch latest eBay sales (uses 1 search)"
                              className="-mt-1 h-8 w-8 rounded font-sans text-[15px] text-muted hover:bg-raised hover:text-ink disabled:opacity-50"
                            >
                              <span className={rowSync[h.id]?.busy ? 'inline-block animate-spin' : ''}>↻</span>
                            </button>
                          )}
                        </span>
                        {rowSync[h.id]?.note && (
                          <span role="status" className={`block font-sans text-[11px] ${rowSync[h.id]?.bad ? 'text-down' : 'text-muted'}`}>
                            {rowSync[h.id]?.note}
                          </span>
                        )}
                        {rowSync[h.id]?.skipped && (
                          <button
                            type="button"
                            className="font-sans text-[11px] text-link hover:text-ink"
                            aria-expanded={Boolean(rowSync[h.id]?.open)}
                            onClick={() => setRowSync((s) => ({ ...s, [h.id]: { ...s[h.id], open: !s[h.id]?.open } }))}
                          >
                            {rowSync[h.id]?.open ? 'Hide skipped' : 'Review skipped →'}
                          </button>
                        )}
                      </td>
                      <td className={`td text-right ${tone(h.unrealized_pnl)}`}>
                        {signedMoney(h.unrealized_pnl)}
                        <span className="block text-[11px]">{pct(h.unrealized_pnl_pct)}</span>
                      </td>
                      <td className="td pr-5 text-right font-sans">
                        {confirmDelete === h.id ? (
                          <span className="inline-flex gap-2">
                            <button className="btn-danger px-3" onClick={() => remove(h.id)}>
                              Delete
                            </button>
                            <button className="btn-ghost px-3" onClick={() => setConfirmDelete(null)}>
                              Keep
                            </button>
                          </span>
                        ) : (
                          <span className="inline-flex gap-2">
                            <button className="btn-ghost px-3" onClick={() => setEditing(h.id)} aria-label={`Edit ${h.title}`}>
                              Edit
                            </button>
                            <button className="btn-ghost px-3" onClick={() => setConfirmDelete(h.id)} aria-label={`Remove ${h.title}`}>
                              Remove
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                    {rowSync[h.id]?.open && rowSync[h.id]?.skipped && (
                      <tr className="bg-base/60">
                        <td colSpan={11} className="px-5 pb-4 pt-2 font-sans">
                          <p className="mb-2 text-[12px] text-muted">
                            eBay sales that didn’t match this card exactly, closest first. If one <b>is</b> this card, press Add — it counts from then on.
                          </p>
                          <ul className="divide-y divide-line rounded-md border border-line">
                            {rowSync[h.id]!.skipped!.map((k) => (
                              <li key={k.url} className="flex flex-wrap items-center gap-3 px-3 py-2 text-[12px]">
                                <span className="num w-16 text-right text-ink">{money(k.total)}</span>
                                <span className="num w-20 text-muted">{k.date}</span>
                                <a href={k.url} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1 truncate text-ink hover:text-link" title={k.title}>
                                  {k.title}
                                </a>
                                <span className="text-warn">{k.why.map((w) => WHY[w] ?? w).join(', ')}</span>
                                {k.added ? (
                                  <span className="w-16 text-center text-up">Added</span>
                                ) : (
                                  <button type="button" className="btn-ghost min-h-8 w-16 px-2 text-[12px]" disabled={k.busy} onClick={() => addSkipped(h, k)}>
                                    {k.busy ? '…' : 'Add'}
                                  </button>
                                )}
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  ),
                )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function HoldingForm({
  draft: initial,
  itemId,
  newCardQuery,
  onSaved,
  onCancel,
}: {
  draft: Draft;
  itemId?: number;
  newCardQuery?: string;
  onSaved: (h: Holding) => void;
  onCancel: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const [creating, setCreating] = useState(Boolean(newCardQuery));
  const guess = newCardQuery ? guessCard(newCardQuery) : {};
  const [photo, setPhoto] = useState<{ content_type: string; data_base64: string; preview: string } | null>(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [picking, setPicking] = useState(false);
  const [sales, setSales] = useState<SaleRow[]>([emptyRow()]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof Draft, v: string | number | null) => setD((x) => ({ ...x, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!d.card_id) {
      setErr('Pick a card first.');
      return;
    }
    setBusy(true);
    setErr(null);
    const graded = d.grade !== 'raw';
    const body = {
      card_id: d.card_id,
      card_parallel_id: d.card_parallel_id,
      is_graded: graded,
      grade_company_id: graded ? (d.grade_company_id ?? PSA_ID) : null,
      grade_value: graded ? d.grade : null,
      condition: graded ? `${d.grader} ${d.grade}` : 'Raw',
      purchase_price: Number(d.purchase_price),
      purchase_date: d.purchase_date,
      quantity: Number(d.quantity),
      notes: d.notes || null,
      image_url: d.image_url.trim() || null,
    };
    try {
      let h = await api<Holding>(itemId ? `/collection/items/${itemId}` : '/collection/items', {
        method: itemId ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      });
      if (photo) {
        h = await api<Holding>(`/collection/items/${h.id}/photo`, {
          method: 'PUT',
          body: JSON.stringify({ content_type: photo.content_type, data_base64: photo.data_base64 }),
        });
      } else if (removePhoto && itemId) {
        h = await api<Holding>(`/collection/items/${h.id}/photo`, { method: 'DELETE' });
      }
      if (validRows(sales).length) {
        const r = await saveSales(h.card_id, sales, h.card_parallel_id);
        if (r.errors.length) setErr(`Some sales weren’t saved: ${r.errors.join(' · ')}`);
        h = await api<Holding>(`/collection/items/${h.id}`);
      }
      onSaved(h);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(c: CardSearchResult) {
    setD((x) => ({ ...x, card_id: c.id, card_title: c.title, card_parallel_id: null, player: c.player }));
  }

  async function choosePhoto(file: File | undefined) {
    if (!file) return;
    setErr(null);
    try {
      setPhoto(await resizeForUpload(file));
      setRemovePhoto(false);
    } catch {
      setErr('Could not read that image. Try a JPG or PNG.');
    }
  }

  const shownPhoto = photo?.preview ?? (removePhoto ? null : d.current_photo) ?? (d.image_url.trim() || null);

  return (
    <div className="panel space-y-4 p-5">
      <p className="panel-title">{itemId ? 'Edit holding' : 'Add a card'}</p>
      {d.card_id ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-base px-3 py-2">
          <span>
            <span className="eyebrow block">Card</span>
            <span className="text-ink">{d.card_title}</span>
          </span>
          {!itemId && (
            <button type="button" className="btn-ghost px-3" onClick={() => set('card_id', null)}>
              Change
            </button>
          )}
        </div>
      ) : creating ? (
        <NewCardForm
          defaults={guess}
          onCancel={() => setCreating(false)}
          onCreated={(c) => {
            setD((x) => ({ ...x, card_id: c.card_id, card_title: c.title, card_parallel_id: c.card_parallel_id, player: guess.player ?? x.player }));
            setCreating(false);
          }}
        />
      ) : (
        <div className="space-y-2">
          <CardPicker onPick={pick} initialQuery={newCardQuery ?? ''} />
          <button type="button" className="text-[13px] text-link hover:text-ink" onClick={() => setCreating(true)}>
            Card not in the catalog? Create it →
          </button>
        </div>
      )}

      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="space-y-1">
            <label htmlFor="hf-grade" className="eyebrow">
              Grade
            </label>
            <select id="hf-grade" className="field" value={d.grade} onChange={(e) => set('grade', e.target.value)}>
              {[...new Set([...GRADES, d.grade])].map((g) => (
                <option key={g} value={g}>
                  {g === 'raw' ? 'Raw' : `${d.grader} ${g}`}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="hf-price" className="eyebrow">
              Paid (each, USD)
            </label>
            <input
              id="hf-price"
              className="field"
              type="number"
              min="0"
              step="0.01"
              required
              value={d.purchase_price}
              onChange={(e) => set('purchase_price', e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="hf-date" className="eyebrow">
              Bought on
            </label>
            <input id="hf-date" className="field" type="date" required value={d.purchase_date} onChange={(e) => set('purchase_date', e.target.value)} />
          </div>
          <div className="space-y-1">
            <label htmlFor="hf-qty" className="eyebrow">
              Quantity
            </label>
            <input id="hf-qty" className="field" type="number" min="1" required value={d.quantity} onChange={(e) => set('quantity', e.target.value)} />
          </div>
        </div>
        <fieldset className="flex flex-wrap items-center gap-4 rounded-md border border-line p-3">
          <legend className="eyebrow px-1">Card photo</legend>
          <button
            type="button"
            onClick={() => setPicking(true)}
            disabled={!d.card_id}
            className="rounded-[4px] hover:ring-2 hover:ring-up disabled:hover:ring-0"
            aria-label="Pick a photo from eBay listings"
            title={d.card_id ? 'Pick a photo from eBay listings' : 'Choose the card first'}
          >
            <CardThumb src={shownPhoto} player={d.player} size="md" alt="Selected card photo" />
          </button>
          <div className="flex min-w-[220px] flex-1 flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-primary" disabled={!d.card_id} onClick={() => setPicking(true)}>
                Pick from eBay
              </button>
              <label className="btn-ghost cursor-pointer">
                {shownPhoto ? 'Upload my own instead' : 'Upload my own'}
                <input type="file" accept="image/*" className="sr-only" onChange={(e) => choosePhoto(e.target.files?.[0])} />
              </label>
              {(photo || (itemId && d.current_photo && !removePhoto && !d.image_url)) && (
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => {
                    setPhoto(null);
                    setRemovePhoto(true);
                  }}
                >
                  Remove photo
                </button>
              )}
            </div>
            <label htmlFor="hf-imgurl" className="sr-only">
              Image URL
            </label>
            <input
              id="hf-imgurl"
              className="field"
              placeholder="…or paste an image URL"
              value={d.image_url}
              onChange={(e) => set('image_url', e.target.value)}
            />
            <p className="text-[12px] text-muted">Click the photo or “Pick from eBay” to choose a listing photo. On a phone, Upload opens the camera.</p>
          </div>
          {picking && d.card_id && (
            <div className="w-full">
              <EbayPhotoPicker
                cardId={d.card_id}
                grade={d.grade === 'raw' ? 'raw' : `${d.grader.toLowerCase()}${d.grade}`}
                onClose={() => setPicking(false)}
                onPick={(url) => {
                  set('image_url', url);
                  setPhoto(null);
                  if (d.current_photo && !d.image_url) setRemovePhoto(true); // replace an uploaded photo
                  setPicking(false);
                  // Also use it as the catalog image if the card has none yet (best effort).
                  api(`/catalog/cards/${d.card_id}/image?only_if_empty=true`, { method: 'PUT', body: JSON.stringify({ image_url: url }) }).catch(() => {});
                }}
              />
            </div>
          )}
        </fieldset>
        <div className="space-y-1">
          <label htmlFor="hf-notes" className="eyebrow">
            Notes
          </label>
          <input id="hf-notes" className="field" value={d.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Optional" />
        </div>
        {d.card_id && (
          <div className="space-y-2 border-t border-line pt-4">
            <p className="eyebrow">{itemId ? 'Add sales for this card (optional)' : 'Recent sales (optional)'}</p>
            <SalesGrid
              rows={sales}
              onChange={setSales}
              defaultGrade={d.grade === 'raw' ? 'Raw' : `PSA ${d.grade}`}
              soldSearchUrl={`https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(d.card_title.replace(/#/g, ''))}&_sacat=261328&LH_Sold=1&LH_Complete=1&_sop=13`}
            />
          </div>
        )}
        {err && <p className="text-[13px] text-down">{err}</p>}
        <div className="flex gap-2">
          <button className="btn-primary" disabled={busy || !d.card_id}>
            {busy ? 'Saving…' : itemId ? 'Save changes' : 'Add to collection'}
          </button>
          <button type="button" className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
