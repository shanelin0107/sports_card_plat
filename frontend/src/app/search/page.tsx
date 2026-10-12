import { EbaySearch } from '@/components/EbaySearch';
import { apiTry } from '@/lib/server-api';
import type { CardSearchResult } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Search eBay · Slab Terminal' };

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = '' } = await searchParams;
  // Cards you already track that match, shown as shortcuts above the eBay results.
  const owned = q ? ((await apiTry<CardSearchResult[]>(`/cards/search?q=${encodeURIComponent(q)}&limit=8`)) ?? []) : [];

  return (
    <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 pb-10 pt-6 sm:px-7">
      <h1 className="text-[22px] font-bold">{q ? <>eBay results for “{q}”</> : 'Search eBay'}</h1>
      <EbaySearch q={q} owned={owned} />
    </main>
  );
}
