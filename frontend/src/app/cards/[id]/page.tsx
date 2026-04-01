import Link from 'next/link';

import SalesHistoryChart from '@/components/SalesHistoryChart';
import { fetchCardComps, fetchCardDetail, fetchCardHistory } from '@/lib/api';

export default async function CardDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ window?: string }>;
}) {
  const { id } = await params;
  const { window = '90d' } = await searchParams;

  const detail = await fetchCardDetail(id);
  const comps = await fetchCardComps(id);
  const history = await fetchCardHistory(id, window);

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <Link href="/" className="text-blue-300">
        ← Back to Dashboard
      </Link>

      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h1 className="text-2xl font-bold">{detail.metadata.title}</h1>
        <p className="text-slate-400">
          {detail.metadata.year} · {detail.metadata.brand} · {detail.metadata.card_set} · #{detail.metadata.card_number}
        </p>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <Metric label="Median" value={`$${detail.stats.median_price ?? 'N/A'}`} />
        <Metric label="Average" value={`$${detail.stats.average_price ?? 'N/A'}`} />
        <Metric label="Comps" value={detail.stats.count} />
        <Metric label="Estimate" value={`$${detail.valuation.estimated_price ?? 'N/A'}`} />
        <Metric label="Range" value={`$${detail.valuation.low_estimate ?? 'N/A'} - $${detail.valuation.high_estimate ?? 'N/A'}`} />
        <Metric label="Confidence" value={detail.valuation.confidence_score} />
      </section>

      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h2 className="mb-2 text-lg font-semibold">Valuation Method</h2>
        <p className="text-sm text-slate-300">{detail.valuation.explanation}</p>
        <p className="text-xs text-slate-400">Reason codes: {(detail.valuation.reason_codes || []).join(', ') || 'N/A'}</p>
      </section>

      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h2 className="mb-2 text-lg font-semibold">Raw vs PSA 10</h2>
        <p>
          Raw median: ${detail.comparison.raw_median ?? 'N/A'} ({detail.comparison.raw_count} comps)
        </p>
        <p>
          PSA 10 median: ${detail.comparison.psa10_median ?? 'N/A'} ({detail.comparison.psa10_count} comps)
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Sales History</h2>
        <div className="flex gap-2 text-sm">
          {['30d', '90d', '1y', 'all'].map((w) => (
            <Link key={w} href={`/cards/${id}?window=${w}`} className="rounded bg-slate-800 px-3 py-1">
              {w.toUpperCase()}
            </Link>
          ))}
        </div>
        <SalesHistoryChart points={history.price_series} />
      </section>

      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h2 className="mb-2 text-lg font-semibold">Latest 10 Comps</h2>
        <ul className="space-y-1 text-sm">
          {comps.length === 0 && <li className="text-slate-400">No comps found for this window.</li>}
          {comps.map((comp: any) => (
            <li key={comp.id}>
              {new Date(comp.sold_at).toISOString().slice(0, 10)} · ${comp.total_price} · Grade {comp.grade_value ?? 'Raw'}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/40 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}
