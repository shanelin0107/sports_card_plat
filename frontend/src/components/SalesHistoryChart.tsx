'use client';

type Point = { date: string; avg_price: number | null; median_price: number | null };

export default function SalesHistoryChart({ points }: { points: Point[] }) {
  const max = Math.max(...points.map((p) => p.avg_price || 0), 1);
  return (
    <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
      <h3 className="font-semibold">Sales History (Average Price)</h3>
      <p className="mb-3 text-sm text-slate-400">Chart-ready series rendered as a compact bar view for MVP demo.</p>
      {points.length === 0 && <p className="text-slate-400">No sales in selected window.</p>}
      <div className="space-y-2">
        {points.map((p) => (
          <div key={p.date} className="grid grid-cols-[100px_1fr_70px] items-center gap-2 text-xs">
            <span className="text-slate-400">{p.date}</span>
            <div className="h-3 rounded bg-blue-500" style={{ width: `${((p.avg_price || 0) / max) * 100}%` }} />
            <span>${p.avg_price ?? 0}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
