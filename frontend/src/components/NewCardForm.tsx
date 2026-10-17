'use client';

import { useState } from 'react';

import { api } from '@/lib/client-api';
import type { CardGuess } from '@/lib/guess-card';
import { SPORTS, normalizeSport } from '@/lib/sports';

type Created = { card_id: number; card_parallel_id: number; title: string; created: boolean };

/** Adds a card to the catalog (player / brand / set are created as needed). */
export function NewCardForm({
  onCreated,
  onCancel,
  defaults = {},
}: {
  onCreated: (c: Created) => void;
  onCancel: () => void;
  defaults?: CardGuess;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr(null);
    try {
      const c = await api<Created>('/catalog/cards', {
        method: 'POST',
        body: JSON.stringify({
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
        }),
      });
      onCreated(c);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const field = (name: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <label htmlFor={`nc-${name}`} className="eyebrow">
        {label}
      </label>
      <input id={`nc-${name}`} name={name} className="field" required defaultValue={(defaults as Record<string, string | undefined>)[name]} {...props} />
    </div>
  );

  return (
    <form onSubmit={submit} className="space-y-3 rounded-md border border-line bg-base/60 p-4">
      <p className="text-[13px] font-bold">New catalog card</p>
      {Object.keys(defaults).length > 0 && <p className="text-[12px] text-muted">Pre-filled from your search — check each field before saving.</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {field('player', 'Player', { placeholder: 'Julio Rodriguez' })}
        {field('year', 'Year', { type: 'number', min: 1880, max: 2100, placeholder: '2023' })}
        {field('brand', 'Brand', { placeholder: 'Topps' })}
        {field('set_name', 'Set', { placeholder: 'Chrome' })}
        {field('card_number', 'Card #', { placeholder: '10' })}
        {field('parallel', 'Parallel', { placeholder: 'Base', required: false })}
        {field('print_run', 'Numbered to (/__)', { type: 'number', min: 1, max: 100000, placeholder: 'e.g. 60', required: false })}
        <div className="space-y-1">
          <label htmlFor="nc-sport" className="eyebrow">
            Sport
          </label>
          <select id="nc-sport" name="sport" className="field" defaultValue={normalizeSport(defaults.sport) ?? 'Baseball'}>
            {SPORTS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="flex items-end gap-5 pb-2 text-[13px]">
          <label className="flex min-h-11 items-center gap-2">
            <input type="checkbox" name="rookie" className="h-4 w-4 accent-up" defaultChecked={defaults.rookie} /> Rookie
          </label>
          <label className="flex min-h-11 items-center gap-2">
            <input type="checkbox" name="autograph" className="h-4 w-4 accent-up" /> Auto
          </label>
        </div>
      </div>
      {err && <p className="text-[13px] text-down">{err}</p>}
      <div className="flex gap-2">
        <button className="btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Create card'}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
