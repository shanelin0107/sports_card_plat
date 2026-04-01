import AboutMVP from '@/components/AboutMVP';
import CollectionPanel from '@/components/CollectionPanel';
import SearchPanel from '@/components/SearchPanel';
import { fetchDashboardDistribution, fetchDashboardSummary, fetchRecentAdditions } from '@/lib/api';

export default async function HomePage() {
  const summary = await fetchDashboardSummary().catch(() => ({
    total_items: 0,
    cost_basis: 0,
    estimated_value: 0,
    unrealized_pnl: 0,
  }));
  const distribution = await fetchDashboardDistribution('brand').catch(() => []);
  const recent = await fetchRecentAdditions().catch(() => []);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h1 className="text-2xl font-bold">Sports Card Intelligence MVP</h1>
        <p className="text-sm text-slate-400">Portfolio demo: deterministic card valuation, comps, collection tracking, and dashboard analytics.</p>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Collection Items" value={summary.total_items} />
        <Metric label="Cost Basis" value={`$${summary.cost_basis}`} />
        <Metric label="Estimated Value" value={`$${summary.estimated_value}`} />
        <Metric label="Unrealized P&L" value={`$${summary.unrealized_pnl}`} />
      </section>

      <AboutMVP />

      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h2 className="mb-2 text-lg font-semibold">Dashboard TODOs (Intentionally Deferred)</h2>
        <p className="text-sm text-slate-400">{summary.todo_daily_change ?? 'TODO: add daily change.'}</p>
        <p className="text-sm text-slate-400">{summary.todo_gainers_losers ?? 'TODO: add gainers/losers.'}</p>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <SearchPanel />
        <CollectionPanel />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
          <h2 className="mb-2 text-lg font-semibold">Holdings Distribution (Brand)</h2>
          {distribution.length === 0 && <p className="text-sm text-slate-400">No distribution data yet.</p>}
          <ul className="space-y-1 text-sm">
            {distribution.map((d: any) => (
              <li key={d.label}>
                {d.label}: {d.count}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
          <h2 className="mb-2 text-lg font-semibold">Recent Additions</h2>
          {recent.length === 0 && <p className="text-sm text-slate-400">No recent additions yet.</p>}
          <ul className="space-y-1 text-sm">
            {recent.map((r: any) => (
              <li key={r.collection_item_id}>
                Card #{r.card_id} · ${r.purchase_price} · {r.purchase_date}
              </li>
            ))}
          </ul>
        </div>
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
