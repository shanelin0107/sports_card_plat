'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { api } from '@/lib/client-api';

type Props = {
  cardId: number;
  player: string;
  year: number;
  cardNumber: string;
  setName: string;
  parallel: string | null;
  printRun: number | null;
  rookie: boolean;
};

/** Fix a catalog card's details (player typo, wrong parallel, missing print run…). */
export function CardEditForm(p: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr(null);
    try {
      await api(`/catalog/cards/${p.cardId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          player: f.get('player'),
          year: Number(f.get('year')),
          card_number: f.get('card_number'),
          set_name: f.get('set_name'),
          parallel: f.get('parallel') || 'Base',
          print_run: f.get('print_run') ? Number(f.get('print_run')) : null,
          rookie: f.get('rookie') === 'on',
        }),
      });
      setOpen(false);
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="text-[12px] text-link hover:text-ink" onClick={() => setOpen(true)}>
        Edit card details
      </button>
    );
  }
  const input = (name: string, label: string, value: string | number | null, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <label htmlFor={`ce-${name}`} className="eyebrow">
        {label}
      </label>
      <input id={`ce-${name}`} name={name} defaultValue={value ?? ''} className="field" {...extra} />
    </div>
  );
  return (
    <form onSubmit={submit} className="mt-3 w-full space-y-3 rounded-md border border-line bg-base/60 p-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {input('player', 'Player', p.player, { required: true })}
        {input('year', 'Year', p.year, { type: 'number', required: true })}
        {input('set_name', 'Set', p.setName, { required: true })}
        {input('card_number', 'Card #', p.cardNumber, { required: true })}
        {input('parallel', 'Parallel', p.parallel ?? 'Base')}
        {input('print_run', 'Numbered to (/__)', p.printRun, { type: 'number', min: 1 })}
        <label className="flex min-h-11 items-center gap-2 self-end text-[13px]">
          <input type="checkbox" name="rookie" defaultChecked={p.rookie} className="h-4 w-4 accent-up" /> Rookie
        </label>
      </div>
      {err && <p className="text-[13px] text-down">{err}</p>}
      <div className="flex gap-2">
        <button className="btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Save card'}
        </button>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
