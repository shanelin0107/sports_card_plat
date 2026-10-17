import { notFound } from 'next/navigation';

import { ErrorState } from '@/components/ErrorState';
import { SetGuide } from '@/components/SetGuide';
import { ApiError, apiGet } from '@/lib/server-api';
import type { SetProduct } from '@/lib/sets';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const p = await apiGet<SetProduct>(`/sets/${Number(id)}`);
    return { title: `${p.name} · Slab Terminal` };
  } catch {
    return { title: 'Set · Slab Terminal' };
  }
}

export default async function SetPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ box?: string; insert?: string }>;
}) {
  const { id } = await params;
  const { box, insert } = await searchParams;
  let product: SetProduct;
  try {
    product = await apiGet<SetProduct>(`/sets/${Number(id)}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    return (
      <main className="mx-auto max-w-[1440px] px-4 pt-6 sm:px-7">
        <ErrorState />
      </main>
    );
  }
  return (
    <main className="mx-auto max-w-[1440px] px-4 pb-10 pt-6 sm:px-7">
      <SetGuide initial={product} initialBox={box} initialInsert={insert ? Number(insert) : undefined} />
    </main>
  );
}
