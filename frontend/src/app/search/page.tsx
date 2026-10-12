import Link from 'next/link';

import { ErrorState } from '@/components/ErrorState';
import { money } from '@/lib/format';
import { apiTry } from '@/lib/server-api';
import type { CardSearchResult } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Search · Slab Terminal' };

const EXAMPLES = ['2023 topps ohtani psa 10', 'wembanyama prizm silver', 'topps chrome #1'];

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = '' } = await searchParams;
  const results = await apiTry<CardSearchResult[]>(`/cards/search?q=${encodeURIComponent(q)}&limit=50`);

  return (
    <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 pb-10 pt-6 sm:px-7">
      <div>
        <h1 className="text-[22px] font-bold">{q ? <>Results for “{q}”</> : 'Card catalog'}</h1>
        <div className="mt-2 flex flex-wrap gap-2 text-[12px]">
          {EXAMPLES.map((e) => (
            <Link key={e} href={`/search?q=${encodeURIComponent(e)}`} className="flex min-h-11 items-center rounded-md bg-raised px-3 font-mono">
              {e}
            </Link>
          ))}
        </div>
      </div>
      {!results ? (
        <ErrorState />
      ) : results.length === 0 ? (
        <p className="text-muted">No cards match. Every word has to appear in the card’s year, set, player, number or grade text.</p>
      ) : (
        <section className="panel" aria-label="Search results">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[13px]">
              <thead>
                <tr>
                  <th className="th pl-5">Card</th>
                  <th className="th">Set</th>
                  <th className="th text-right">Comps</th>
                  <th className="th pr-5 text-right">Est.</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {results.map((r) => (
                  <tr key={r.id} className="border-t border-line hover:bg-raised/50">
                    <td className="td pl-5 font-sans">
                      <Link href={`/cards/${r.id}`} className="flex min-h-11 flex-col justify-center text-ink hover:text-link">
                        <b>{r.player}</b>
                        <span className="text-[12px] text-muted">
                          {r.year} #{r.card_number} {r.rookie_flag ? '· RC' : ''}
                        </span>
                      </Link>
                    </td>
                    <td className="td font-sans">{r.card_set}</td>
                    <td className="td text-right">{r.comp_count}</td>
                    <td className="td pr-5 text-right">{money(r.valuation_preview)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
