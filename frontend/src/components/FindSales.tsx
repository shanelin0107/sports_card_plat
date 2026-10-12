'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/client-api';

type Links = { query: string; links: { name: string; url: string; note: string }[] };

const GRADERS = ['PSA', 'BGS', 'SGC', 'CGC'];
const GRADES = ['raw', '10', '9.5', '9', '8.5', '8', '7', '6', '5', '4', '3', '2', '1'];

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/** Links to where sold prices live + a quick form to record a sale you found. */
export function FindSales({ cardId, grade, onAdded }: { cardId: number; grade: string; onAdded: () => void }) {
  const [links, setLinks] = useState<Links | null>(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const defaultGrade = grade.startsWith('psa') ? grade.slice(3) : 'raw';

  useEffect(() => {
    api<Links>(`/market/sold-links/${cardId}?grade=${grade}`)
      .then(setLinks)
      .catch(() => {});
  }, [cardId, grade]);

  async function copy() {
    if (!links) return;
    try {
      await navigator.clipboard.writeText(links.query);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked; the text is visible anyway */
    }
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const g = String(f.get('grade'));
    setBusy(true);
    setMsg(null);
    try {
      await api(`/market/sales/${cardId}`, {
        method: 'POST',
        body: JSON.stringify({
          price: Number(f.get('price')),
          shipping: f.get('shipping') ? Number(f.get('shipping')) : null,
          date: f.get('date'),
          grade: g === 'raw' ? 'Raw' : `${f.get('grader')} ${g}`,
          url: String(f.get('url') || '').trim() || null,
        }),
      });
      setMsg({ ok: true, text: 'Sale added — chart, median and last sale updated.' });
      (form.elements.namedItem('price') as HTMLInputElement).value = '';
      (form.elements.namedItem('shipping') as HTMLInputElement).value = '';
      (form.elements.namedItem('url') as HTMLInputElement).value = '';
      onAdded();
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="eyebrow mr-1">Find sales</span>
        {links?.links.map((l) => (
          <a key={l.name} href={l.url} target="_blank" rel="noopener noreferrer" title={l.note} className="btn-ghost min-h-9 px-3 text-[12px]">
            {l.name} ↗
          </a>
        ))}
        {links && (
          <button type="button" onClick={copy} className="min-h-9 px-2 font-mono text-[11px] text-muted hover:text-ink" title="Copy search text">
            {copied ? 'copied ✓' : `copy “${links.query}”`}
          </button>
        )}
        <button type="button" className="btn-primary ml-auto min-h-9 px-3 text-[12px]" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? 'Close' : '+ Add a sale'}
        </button>
      </div>

      {open && (
        <form onSubmit={submit} className="space-y-3 border-t border-line pt-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
            <div className="col-span-2 space-y-1 md:col-span-6">
              <label htmlFor="fs-url" className="eyebrow">
                Listing link (optional — eBay link prevents duplicates)
              </label>
              <input id="fs-url" name="url" className="field" placeholder="https://www.ebay.com/itm/…" inputMode="url" />
            </div>
            <div className="space-y-1">
              <label htmlFor="fs-price" className="eyebrow">
                Sold for
              </label>
              <input id="fs-price" name="price" type="number" min="0.01" step="0.01" required className="field" placeholder="0.00" />
            </div>
            <div className="space-y-1">
              <label htmlFor="fs-ship" className="eyebrow">
                Shipping
              </label>
              <input id="fs-ship" name="shipping" type="number" min="0" step="0.01" className="field" placeholder="0.00" />
            </div>
            <div className="space-y-1">
              <label htmlFor="fs-date" className="eyebrow">
                Sale date
              </label>
              <input id="fs-date" name="date" type="date" required max={today()} defaultValue={today()} className="field" />
            </div>
            <div className="space-y-1">
              <label htmlFor="fs-grader" className="eyebrow">
                Grader
              </label>
              <select id="fs-grader" name="grader" className="field" defaultValue="PSA">
                {GRADERS.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor="fs-grade" className="eyebrow">
                Grade
              </label>
              <select id="fs-grade" name="grade" className="field" defaultValue={GRADES.includes(defaultGrade) ? defaultGrade : 'raw'}>
                {GRADES.map((g) => (
                  <option key={g} value={g}>
                    {g === 'raw' ? 'Raw' : g}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button className="btn-primary w-full" disabled={busy}>
                {busy ? 'Saving…' : 'Save sale'}
              </button>
            </div>
          </div>
          <p className="text-[12px] text-muted">Tip: on eBay sold results, a green price with a strikethrough means Best Offer — 130point shows the real accepted price.</p>
        </form>
      )}
      {msg && (
        <p className={`text-[12px] ${msg.ok ? 'text-up' : 'text-down'}`} role="status">
          {msg.text}
        </p>
      )}
    </div>
  );
}
