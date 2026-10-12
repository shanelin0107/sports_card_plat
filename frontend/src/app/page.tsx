import { ErrorState } from '@/components/ErrorState';
import { HoldingsBoard } from '@/components/HoldingsBoard';
import { IngestionPanel } from '@/components/IngestionPanel';
import { Kpi } from '@/components/Kpi';
import { RecentComps } from '@/components/RecentComps';
import { Ticker } from '@/components/Ticker';
import { money, pct, signedMoney, tone } from '@/lib/format';
import { apiTry } from '@/lib/server-api';
import type { Holding, RecentComp, SourceHealth, Summary } from '@/lib/types';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  const [summary, holdings, comps, health] = await Promise.all([
    apiTry<Summary>('/dashboard/summary'),
    apiTry<Holding[]>('/collection/items'),
    apiTry<RecentComp[]>('/dashboard/recent-comps?limit=8'),
    apiTry<SourceHealth>('/internal/ingestion/source-health'),
  ]);

  if (!summary || !holdings) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7">
        <ErrorState />
      </main>
    );
  }

  const movers = [...summary.gainers, ...summary.losers];

  return (
    <>
      <Ticker holdings={holdings} health={health} />
      <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 pb-10 pt-6 sm:px-7">
        <h1 className="sr-only">Portfolio dashboard</h1>
        <section aria-label="Portfolio summary" className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          <Kpi
            label="Estimated value"
            value={money(summary.estimated_value)}
            sub={
              summary.daily_change !== null ? (
                <span className={tone(summary.daily_change)}>
                  {signedMoney(summary.daily_change)} ({pct(summary.daily_change_pct)}) since last snapshot
                </span>
              ) : (
                'Daily change starts after the first full day of snapshots'
              )
            }
          />
          <Kpi label="Cost basis" value={money(summary.cost_basis)} sub={`${summary.total_items} cards · ${summary.positions} positions`} />
          <Kpi
            label="Unrealized P&L"
            value={
              <>
                {signedMoney(summary.unrealized_pnl)} <span className="text-[16px]">{pct(summary.unrealized_pnl_pct)}</span>
              </>
            }
            valueClass={tone(summary.unrealized_pnl)}
            sub={summary.unpriced_positions ? `${summary.unpriced_positions} position(s) have no comps yet` : 'All positions priced from sold comps'}
          />
          <Kpi
            label="Holdings"
            value={
              <>
                {summary.positions} <span className="text-[14px] text-muted">positions · {summary.graded_positions} graded</span>
              </>
            }
            sub={
              movers.length ? (
                <span>
                  Top mover: {movers[0].title.replace(/^\d{4} /, '').slice(0, 28)}{' '}
                  <span className={tone(movers[0].change)}>{signedMoney(movers[0].change)}</span>
                </span>
              ) : (
                `As of ${summary.as_of}`
              )
            }
          />
        </section>

        <HoldingsBoard holdings={holdings} />

        <div className="flex flex-wrap gap-5">
          <RecentComps comps={comps ?? []} />
          <IngestionPanel health={health} />
        </div>
      </main>
    </>
  );
}
