'use client';

import Link from 'next/link';
import { useState } from 'react';

type CardResult = {
  id: number;
  title: string;
  year: number;
  card_number: string;
  brand: string;
  card_set: string;
  player: string;
  default_image_url?: string;
  valuation_preview?: number;
};

const EXAMPLE_QUERIES = ['2023 topps ohtani psa 10', 'wembanyama prizm silver', 'topps chrome #1'];

export default function SearchPanel() {
  const [query, setQuery] = useState(EXAMPLE_QUERIES[0]);
  const [results, setResults] = useState<CardResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);

  async function runSearch(nextQuery?: string) {
    const actualQuery = nextQuery ?? query;
    setQuery(actualQuery);
    setLoading(true);
    const base = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
    const res = await fetch(`${base}/api/v1/cards/search?q=${encodeURIComponent(actualQuery)}`);
    const data = await res.json();
    setResults(data);
    setSearched(true);
    setLoading(false);
  }

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
      <h2 className="text-lg font-semibold">Card Search</h2>
      <p className="mb-3 text-sm text-slate-400">Search by player, brand, set, card #, or grade hints.</p>

      <div className="mb-2 flex gap-2">
        <input
          className="w-full rounded border border-slate-700 bg-slate-950 p-2"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Try: 2023 topps ohtani psa 10"
        />
        <button className="rounded bg-blue-600 px-4 font-medium" onClick={() => runSearch()} disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        {EXAMPLE_QUERIES.map((q) => (
          <button key={q} className="rounded bg-slate-800 px-2 py-1 text-slate-300" onClick={() => runSearch(q)}>
            {q}
          </button>
        ))}
      </div>

      {searched && results.length === 0 && <p className="text-sm text-slate-400">No cards matched your query.</p>}
      <ul className="space-y-2 text-sm">
        {results.map((card) => (
          <li key={card.id} className="rounded border border-slate-700 bg-slate-950 p-3">
            <Link href={`/cards/${card.id}`} className="font-semibold text-blue-300">
              {card.title}
            </Link>
            <p className="text-slate-400">
              {card.year} · {card.brand} · {card.card_set} · #{card.card_number}
            </p>
            <p className="text-slate-400">{card.player}</p>
            <p className="text-emerald-300">Valuation preview: {card.valuation_preview ? `$${card.valuation_preview}` : 'N/A'}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
