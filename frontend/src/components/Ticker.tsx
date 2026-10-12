import type { Holding, SourceHealth } from '@/lib/types';
import { money, pct, tickerName, tone } from '@/lib/format';

export function Ticker({ holdings, health }: { holdings: Holding[]; health: SourceHealth | null }) {
  const run = health?.last_run;
  const openIssues = health ? Object.values(health.open_issues).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="border-b border-line">
      <div className="mx-auto flex max-w-[1440px] gap-8 overflow-x-auto whitespace-nowrap px-4 py-2.5 font-mono text-[12px] text-muted sm:px-7">
        {holdings.map((h) => (
          <span key={h.id}>
            {tickerName(h.player)} {String(h.year ?? '').slice(2)} #{h.card_number} {h.grade_label.replace(' ', '')}{' '}
            <b className="text-ink">{money(h.estimated_unit_price)}</b>{' '}
            <span className={tone(h.unrealized_pnl_pct)}>
              {h.unrealized_pnl_pct !== null ? (h.unrealized_pnl_pct >= 0 ? '▲ ' : '▼ ') : ''}
              {pct(h.unrealized_pnl_pct)}
            </span>
          </span>
        ))}
        {run && (
          <span>
            LAST INGEST{' '}
            <b className="text-ink">
              {run.mode} · {run.promoted_count} promoted · {openIssues} to review
            </b>
          </span>
        )}
      </div>
    </div>
  );
}
