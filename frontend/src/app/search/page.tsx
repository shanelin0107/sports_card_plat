import Link from 'next/link';

import { AiPricePanel } from '@/components/AiPricePanel';
import { CardThumb } from '@/components/CardThumb';
import { EbayMarketPanel } from '@/components/EbayMarketPanel';
import { ErrorState } from '@/components/ErrorState';
import { money } from '@/lib/format';
import { cardImage } from '@/lib/images';
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
      {results && results.length > 0 && q && (
        <p className="-mt-2 text-[13px] text-muted">
          Not the card you meant?{' '}
          <Link href={`/collection?new=${encodeURIComponent(q)}`} className="text-link hover:text-ink">
            Create “{q}” →
          </Link>
        </p>
      )}
      {!results ? (
        <ErrorState />
      ) : results.length === 0 ? (
        q ? (
          <>
            <div className="panel space-y-3 p-5">
              <p className="font-bold">“{q}” isn’t in your catalog yet.</p>
              <p className="text-[13px] text-muted">
                Search looks through the cards you’ve added — it isn’t connected to an outside card database. Ask AI for prices below, or add the
                card to your catalog so it shows up here, on your dashboard, and in sales matching.
              </p>
              <Link href={`/collection?new=${encodeURIComponent(q)}`} className="btn-primary text-[#06281A] hover:text-[#06281A]">
                + Create this card
              </Link>
            </div>
            <EbayMarketPanel query={q} />
            <AiPricePanel query={q} />
          </>
        ) : (
          <p className="text-muted">Your catalog is empty. Add a card from the Collection page.</p>
        )
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
                      <Link href={`/cards/${r.id}`} className="flex min-h-11 items-center gap-3 text-ink hover:text-link">
                        <CardThumb src={cardImage(r)} player={r.player} />
                        <span className="flex flex-col">
                          <b>{r.player}</b>
                          <span className="text-[12px] text-muted">
                            {r.year} #{r.card_number} {r.rookie_flag ? '· RC' : ''}
                          </span>
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
