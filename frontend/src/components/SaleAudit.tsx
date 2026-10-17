'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money } from '@/lib/format';

type Suspect = { comp_id: number; card_id: number; card: string; title: string; url: string | null; total: number; date: string | null; why: string[] };

const WHY: Record<string, string> = {
  player: 'different player',
  'card #': 'different card #',
  parallel: 'different parallel',
  'print run': 'different print run',
  year: 'different year',
  set: 'different set',
  'not a single card': 'lot / break / sealed',
};

/** Sales that were saved automatically but that today's matching rules say belong to a
 *  different card. Nothing is removed until the owner presses Remove. */
export function SaleAudit() {
  const [items, setItems] = useState<Suspect[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<number | 'all' | null>(null);
  const [removed, setRemoved] = useState(0);
  const [confirmAll, setConfirmAll] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ suspects: Suspect[] }>('/market/sale-audit')
      .then((r) => setItems(r.suspects))
      .catch(() => setItems([]));
  }, []);

  async function remove(list: Suspect[]) {
    setErr(null);
    for (const s of list) {
      try {
        await api(`/cards/${s.card_id}/comps/${s.comp_id}`, { method: 'DELETE' });
        setItems((xs) => (xs ?? []).filter((x) => x.comp_id !== s.comp_id));
        setRemoved((n) => n + 1);
      } catch (e) {
        setErr((e as Error).message);
        break;
      }
    }
  }

  if (!items || (items.length === 0 && removed === 0)) return null;

  return (
    <section className="panel mb-5 border-warn/40 p-4" aria-label="Sales to review">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px]">
          {items.length > 0 ? (
            <>
              <b className="text-warn">{items.length} automatically saved sale{items.length === 1 ? '' : 's'}</b> look like a different card (e.g. a
              numbered parallel or another player). They may be pulling your estimates off.
            </>
          ) : (
            <span className="text-up">Removed {removed} sale{removed === 1 ? '' : 's'}.</span>
          )}
        </p>
        <div className="flex gap-2">
          {removed > 0 && (
            <button type="button" className="btn-ghost text-[13px]" onClick={() => window.location.reload()}>
              Reload to update estimates
            </button>
          )}
          {items.length > 0 && (
            <button type="button" className="btn-ghost text-[13px]" onClick={() => setOpen(!open)} aria-expanded={open}>
              {open ? 'Hide' : 'Review'}
            </button>
          )}
        </div>
      </div>
      {open && items.length > 0 && (
        <div className="mt-3 space-y-2">
          <ul className="divide-y divide-line text-[12px]">
            {items.map((s) => (
              <li key={s.comp_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <div className="min-w-0 flex-1">
                  <Link href={`/cards/${s.card_id}`} className="block truncate font-bold text-ink hover:text-link">
                    {s.card}
                  </Link>
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="block truncate text-muted hover:text-link" title={s.title}>
                      {s.title}
                    </a>
                  ) : (
                    <span className="block truncate text-muted">{s.title}</span>
                  )}
                </div>
                <span className="font-mono text-warn">{s.why.map((w) => WHY[w] ?? w).join(', ')}</span>
                <span className="w-[90px] text-right font-mono">{money(s.total)}</span>
                <span className="w-[100px] text-muted">{s.date ? longDate(s.date) : ''}</span>
                <button
                  type="button"
                  className="text-link hover:text-ink disabled:text-muted"
                  disabled={busy !== null}
                  onClick={async () => {
                    setBusy(s.comp_id);
                    await remove([s]);
                    setBusy(null);
                  }}
                >
                  {busy === s.comp_id ? 'Removing…' : 'Remove'}
                </button>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            {confirmAll ? (
              <>
                <span className="text-[12px]">Remove all {items.length} from their cards?</span>
                <button
                  type="button"
                  className="btn-primary text-[13px]"
                  disabled={busy !== null}
                  onClick={async () => {
                    setBusy('all');
                    await remove(items);
                    setBusy(null);
                    setConfirmAll(false);
                  }}
                >
                  {busy === 'all' ? 'Removing…' : 'Yes, remove all'}
                </button>
                <button type="button" className="btn-ghost text-[13px]" onClick={() => setConfirmAll(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <button type="button" className="btn-ghost text-[13px]" onClick={() => setConfirmAll(true)}>
                Remove all listed…
              </button>
            )}
            <span className="text-[11px] text-muted">A removed sale isn’t added back automatically; you can still add it by hand on the card page.</span>
          </div>
          {err && <p className="text-[12px] text-down">Couldn’t remove: {err}</p>}
        </div>
      )}
    </section>
  );
}
