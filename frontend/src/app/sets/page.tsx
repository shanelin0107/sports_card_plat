import Link from 'next/link';

import { ErrorState } from '@/components/ErrorState';
import { SetImportForm } from '@/components/SetImportForm';
import { apiTry } from '@/lib/server-api';
import type { SetSummary } from '@/lib/sets';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Sets · Slab Terminal' };

export default async function SetsPage() {
  const sets = await apiTry<SetSummary[]>('/sets');
  return (
    <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 pb-10 pt-6 sm:px-7">
      <div>
        <h1 className="text-[22px] font-bold">Insert &amp; SSP guide</h1>
        <p className="mt-1 text-[13px] text-muted">The rare inserts in a product, how often they fall in each box, and what they sell for.</p>
      </div>
      {!sets ? (
        <ErrorState />
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
          {sets.map((s) => (
            <li key={s.id}>
              <Link href={`/sets/${s.id}`} className="panel block p-4 text-ink hover:border-edge hover:bg-raised">
                <p className="eyebrow">{s.sport}</p>
                <p className="mt-1 text-[16px] font-bold">{s.name}</p>
                <p className="mt-2 font-mono text-[12px] text-muted">
                  {s.inserts} inserts · {s.cards} cards
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <SetImportForm />
    </main>
  );
}
