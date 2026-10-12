import Link from 'next/link';

import { money, shortDate } from '@/lib/format';
import type { RecentComp } from '@/lib/types';

export function RecentComps({ comps }: { comps: RecentComp[] }) {
  return (
    <section aria-label="Recent sales" className="panel min-w-0 flex-[2_1_520px]">
      <div className="panel-head">
        <h2 className="panel-title">Recent sold comps</h2>
        <Link href="/search" className="text-[13px]">
          Search comps →
        </Link>
      </div>
      {comps.length === 0 ? (
        <p className="p-5 text-muted">No sales recorded yet. Run an ingest to pull sold listings.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse font-mono text-[12px]">
            <tbody>
              {comps.map((c) => (
                <tr key={c.id} className="border-b border-line last:border-0">
                  <td className="py-2.5 pl-5 pr-3 text-muted">{shortDate(c.sold_at)}</td>
                  <td className="px-3">
                    <Link href={`/cards/${c.card_id}`} className="text-ink hover:text-link">
                      {c.title.replace(/^\d{4} /, '').replace(/ RC$/, '')}
                    </Link>
                  </td>
                  <td className="px-3">{c.grade_label}</td>
                  <td className="py-2.5 pl-3 pr-5 text-right">{money(c.total_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
