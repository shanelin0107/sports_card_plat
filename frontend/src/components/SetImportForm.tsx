'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { api } from '@/lib/client-api';

type ImportResult = {
  product_id: number | null;
  updated: { name: string; cards: number; odds: number }[];
  unmatched: string[];
  warnings: string[];
};

/** Read a checklist page and an odds page (Playwright on the server) into the set guide. */
export function SetImportForm({ product }: { product?: { name: string; checklist_url: string | null; odds_url: string | null } }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<ImportResult | null>(null);
  const [open, setOpen] = useState(!product);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr(null);
    setRes(null);
    try {
      const r = await api<ImportResult>('/sets/import', {
        method: 'POST',
        body: JSON.stringify({
          name: product?.name ?? f.get('name'),
          checklist_url: String(f.get('checklist_url') || '') || null,
          odds_url: String(f.get('odds_url') || '') || null,
        }),
      });
      setRes(r);
      if (r.product_id && r.updated.length) {
        if (product) router.refresh();
        else router.push(`/sets/${r.product_id}`);
      }
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn-ghost text-[13px]" onClick={() => setOpen(true)}>
        Re-import checklist &amp; odds…
      </button>
    );
  }

  return (
    <section className="panel space-y-3 p-4" aria-label="Import a set">
      <div>
        <p className="font-bold">{product ? 'Re-import checklist & odds' : 'Add a product'}</p>
        <p className="mt-1 text-[12px] text-muted">
          The server opens these pages in a headless browser and reads the checklist rows (e.g. <span className="font-mono text-ink">FAN-1 Victor Wembanyama – San Antonio Spurs</span>) and the
          pack odds (e.g. <span className="font-mono text-ink">1:144 mega packs</span>). Sites that show a bot check are skipped. Takes ~10–30 seconds.
        </p>
      </div>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        {!product && (
          <label className="space-y-1 sm:col-span-2">
            <span className="eyebrow">Product</span>
            <input name="name" required minLength={6} className="field" placeholder="2025-26 Topps Chrome Basketball" />
          </label>
        )}
        <label className="space-y-1">
          <span className="eyebrow">Checklist page</span>
          <input name="checklist_url" type="url" className="field" defaultValue={product?.checklist_url ?? ''} placeholder="https://www.checklistcenter.com/…" />
        </label>
        <label className="space-y-1">
          <span className="eyebrow">Odds page</span>
          <input name="odds_url" type="url" className="field" defaultValue={product?.odds_url ?? ''} placeholder="https://www.beckett.com/news/…" />
        </label>
        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <button className="btn-primary" disabled={busy}>
            {busy ? 'Reading pages…' : 'Import'}
          </button>
          {product && (
            <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
          )}
        </div>
      </form>
      {err && <p className="text-[13px] text-down">Import failed: {err}</p>}
      {res && (
        <div className="space-y-1 text-[13px]">
          {res.updated.length > 0 ? (
            <p className="text-up">
              Updated {res.updated.map((u) => `${u.name} (${u.cards} cards, ${u.odds} odds)`).join(' · ')}
            </p>
          ) : (
            <p className="text-warn">Nothing was updated.</p>
          )}
          {res.warnings.map((w) => (
            <p key={w} className="text-warn">
              {w}
            </p>
          ))}
          {res.unmatched.length > 0 && <p className="text-muted">Other sets on the page (not SSPs here): {res.unmatched.join(', ')}</p>}
        </div>
      )}
    </section>
  );
}
