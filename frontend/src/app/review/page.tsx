import { ReviewQueue } from '@/components/ReviewQueue';
import { apiTry } from '@/lib/server-api';
import type { IngestionRun } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Ingestion review · Slab Terminal' };

export default async function ReviewPage() {
  const runs = (await apiTry<IngestionRun[]>('/internal/ingestion/runs?limit=10')) ?? [];
  return (
    <main className="mx-auto max-w-[1440px] px-4 pb-10 pt-6 sm:px-7">
      <ReviewQueue initialRuns={runs} />
    </main>
  );
}
