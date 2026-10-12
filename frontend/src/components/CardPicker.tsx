'use client';

import { useEffect, useId, useState } from 'react';

import { api } from '@/lib/client-api';
import { money } from '@/lib/format';
import type { CardSearchResult } from '@/lib/types';

/** Debounced catalog search that returns the chosen card. */
export function CardPicker({
  onPick,
  initialQuery = '',
  label = 'Find card in catalog',
}: {
  onPick: (c: CardSearchResult) => void;
  initialQuery?: string;
  label?: string;
}) {
  const id = useId();
  const [q, setQ] = useState(initialQuery);
  const [results, setResults] = useState<CardSearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      setLoading(true);
      api<CardSearchResult[]>(`/cards/search?q=${encodeURIComponent(q)}&limit=8`)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="eyebrow">
        {label}
      </label>
      <input id={id} className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Player, set, year or #" autoComplete="off" />
      {loading && <p className="text-[12px] text-muted">Searching…</p>}
      {results.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-md border border-line">
          {results.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onPick(r)}
                className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-raised"
              >
                <span>
                  <span className="text-ink">{r.title}</span>
                  <span className="block text-[12px] text-muted">
                    {r.comp_count} comps{r.valuation_preview !== null ? ` · ~${money(r.valuation_preview)}` : ''}
                  </span>
                </span>
                <span className="text-[12px] text-link">Select</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!loading && q.trim().length >= 2 && results.length === 0 && <p className="text-[12px] text-muted">No catalog match.</p>}
    </div>
  );
}
