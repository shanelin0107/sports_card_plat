'use client';

import Link from 'next/link';
import { useState } from 'react';

import { api } from '@/lib/client-api';
import { money, pct, signedMoney, tone } from '@/lib/format';
import type { CardSearchResult, Holding } from '@/lib/types';

import { CardPicker } from './CardPicker';
import { NewCardForm } from './NewCardForm';

const GRADES = ['raw', '10', '9', '8', '7', '6', '5', '4', '3', '2', '1'];
const PSA_ID = 1;

type Draft = {
  card_id: number | null;
  card_title: string;
  card_parallel_id: number | null;
  grade: string;
  purchase_price: string;
  purchase_date: string;
  quantity: string;
  notes: string;
};

const today = () => new Date().toISOString().slice(0, 10);

function blank(): Draft {
  return { card_id: null, card_title: '', card_parallel_id: null, grade: 'raw', purchase_price: '', purchase_date: today(), quantity: '1', notes: '' };
}

function fromHolding(h: Holding): Draft {
  return {
    card_id: h.card_id,
    card_title: h.title ?? `Card ${h.card_id}`,
    card_parallel_id: h.card_parallel_id,
    grade: h.grade_value ?? 'raw',
    purchase_price: String(h.purchase_price),
    purchase_date: h.purchase_date,
    quantity: String(h.quantity),
    notes: h.notes ?? '',
  };
}

export function CollectionManager({ initial, startAdding }: { initial: Holding[]; startAdding: boolean }) {
  const [items, setItems] = useState(initial);
  const [editing, setEditing] = useState<number | 'new' | null>(startAdding ? 'new' : null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }

  const totalCost = items.reduce((s, h) => s + h.purchase_price * h.quantity, 0);
  const totalEst = items.reduce((s, h) => s + (h.estimated_value ?? 0), 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold">Collection</h1>
          <p className="num mt-1 text-[13px] text-muted">
            {items.length} positions · cost {money(totalCost)} · est. {money(totalEst)} ·{' '}
            <span className={tone(totalEst - totalCost)}>{signedMoney(totalEst - totalCost)}</span>
          </p>
        </div>
        {editing !== 'new' && (
          <button className="btn-primary" onClick={() => setEditing('new')}>
            + Add card
          </button>
        )}
      </div>

      {editing === 'new' && <HoldingForm draft={blank()} onSaved={(h) => saved(h, true)} onCancel={() => setEditing(null)} />}
      {error && <p className="text-[13px] text-down">{error}</p>}

      <section className="panel" aria-label="All holdings">
        {items.length === 0 ? (
          <p className="p-5 text-muted">Nothing here yet — add your first card above.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse text-[13px]">
              <thead>
                <tr>
                  <th className="th pl-5">Card</th>
                  <th className="th">Grade</th>
                  <th className="th text-right">Qty</th>
                  <th className="th text-right">Paid</th>
                  <th className="th">Bought</th>
                  <th className="th text-right">Est.</th>
                  <th className="th text-right">P&amp;L</th>
                  <th className="th pr-5 text-right">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {items.map((h) =>
                  editing === h.id ? (
                    <tr key={h.id} className="border-t border-line">
                      <td colSpan={8} className="p-4">
                        <HoldingForm draft={fromHolding(h)} itemId={h.id} onSaved={(x) => saved(x, false)} onCancel={() => setEditing(null)} />
                      </td>
                    </tr>
                  ) : (
                    <tr key={h.id} className="border-t border-line">
                      <td className="td pl-5 font-sans">
                        <Link href={`/cards/${h.card_id}?grade=${h.grade_value ? `psa${h.grade_value}` : 'raw'}`} className="text-ink hover:text-link">
                          <b>{h.player}</b>
                        </Link>
                        {h.rookie_flag && <span className="badge ml-1.5 bg-warn/15 text-warn">RC</span>}
                        <br />
                        <span className="text-[12px] text-muted">
                          {h.year} {h.card_set} #{h.card_number}
                          {h.parallel && h.parallel !== 'Base' ? ` · ${h.parallel}` : ''}
                        </span>
                        {h.notes && <span className="block text-[12px] italic text-muted">{h.notes}</span>}
                      </td>
                      <td className="td">{h.grade_label}</td>
                      <td className="td text-right">{h.quantity}</td>
                      <td className="td text-right">{money(h.purchase_price)}</td>
                      <td className="td text-muted">{h.purchase_date}</td>
                      <td className="td text-right">{money(h.estimated_value)}</td>
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
                  ),
                )}
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
  onSaved,
  onCancel,
}: {
  draft: Draft;
  itemId?: number;
  onSaved: (h: Holding) => void;
  onCancel: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const [creating, setCreating] = useState(false);
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
      grade_company_id: graded ? PSA_ID : null,
      grade_value: graded ? d.grade : null,
      condition: graded ? `PSA ${d.grade}` : 'Raw',
      purchase_price: Number(d.purchase_price),
      purchase_date: d.purchase_date,
      quantity: Number(d.quantity),
      notes: d.notes || null,
    };
    try {
      const h = await api<Holding>(itemId ? `/collection/items/${itemId}` : '/collection/items', {
        method: itemId ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      });
      onSaved(h);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(c: CardSearchResult) {
    setD((x) => ({ ...x, card_id: c.id, card_title: c.title, card_parallel_id: null }));
  }

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
          onCancel={() => setCreating(false)}
          onCreated={(c) => {
            setD((x) => ({ ...x, card_id: c.card_id, card_title: c.title, card_parallel_id: c.card_parallel_id }));
            setCreating(false);
          }}
        />
      ) : (
        <div className="space-y-2">
          <CardPicker onPick={pick} />
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
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  {g === 'raw' ? 'Raw' : `PSA ${g}`}
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
        <div className="space-y-1">
          <label htmlFor="hf-notes" className="eyebrow">
            Notes
          </label>
          <input id="hf-notes" className="field" value={d.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Optional" />
        </div>
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
