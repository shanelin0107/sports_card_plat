import { CollectionManager } from '@/components/CollectionManager';
import { ErrorState } from '@/components/ErrorState';
import { apiTry } from '@/lib/server-api';
import type { Holding } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Collection · Slab Terminal' };

export default async function CollectionPage({ searchParams }: { searchParams: Promise<{ add?: string; new?: string }> }) {
  const { add, new: newCardQuery } = await searchParams;
  const holdings = await apiTry<Holding[]>('/collection/items');
  return (
    <main className="mx-auto max-w-[1440px] px-4 pb-10 pt-6 sm:px-7">
      {holdings ? <CollectionManager initial={holdings} startAdding={add === '1'} newCardQuery={newCardQuery} /> : <ErrorState />}
    </main>
  );
}
