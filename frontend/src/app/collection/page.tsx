import { CollectionManager } from '@/components/CollectionManager';
import { ErrorState } from '@/components/ErrorState';
import { SaleAudit } from '@/components/SaleAudit';
import { viewFromParams } from '@/lib/collection-view';
import { apiTry } from '@/lib/server-api';
import type { Holding } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Collection · Slab Terminal' };

export default async function CollectionPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const { add, new: newCardQuery } = params;
  const view = viewFromParams(new URLSearchParams(Object.entries(params).filter((kv): kv is [string, string] => typeof kv[1] === 'string')));
  const holdings = await apiTry<Holding[]>('/collection/items');
  return (
    <main className="mx-auto max-w-[1440px] px-4 pb-10 pt-6 sm:px-7">
      {holdings && <SaleAudit />}
      {holdings ? <CollectionManager initial={holdings} startAdding={add === '1'} newCardQuery={newCardQuery} initialView={view} /> : <ErrorState />}
    </main>
  );
}
