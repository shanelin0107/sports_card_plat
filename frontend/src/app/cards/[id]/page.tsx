import Link from 'next/link';
import { notFound } from 'next/navigation';

import { AiPricePanel } from '@/components/AiPricePanel';
import { CardEditForm } from '@/components/CardEditForm';
import { CardThumb } from '@/components/CardThumb';
import { EbayMarketPanel } from '@/components/EbayMarketPanel';
import { ErrorState } from '@/components/ErrorState';
import { Kpi } from '@/components/Kpi';
import { MarketTrend } from '@/components/MarketTrend';
import { confidenceLabel, longDate, money } from '@/lib/format';
import { cardImage } from '@/lib/images';
import { ApiError, apiGet } from '@/lib/server-api';
import type { CardDetail } from '@/lib/types';

export const dynamic = 'force-dynamic';

const WINDOWS = ['30d', '90d', '1y', 'all'];

export default async function CardDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ window?: string; grade?: string }>;
}) {
  const { id } = await params;
  const { window = '30d', grade } = await searchParams;
  if (!/^\d+$/.test(id)) notFound();

  let detail: CardDetail;
  try {
    detail = await apiGet<CardDetail>(`/cards/${id}?window=${window}${grade ? `&grade=${grade}` : ''}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    return (
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7">
        <ErrorState />
      </main>
    );
  }

  const activeGrade = grade ?? detail.grades.find((g) => g.label === detail.valuation.grade)?.key ?? 'all';
  const m = detail.metadata;
  const v = detail.valuation;
  const conf = confidenceLabel(v.confidence_score);
  const href = (g: string, w: string) => `/cards/${id}?grade=${g}&window=${w}`;

  return (
    <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 pb-10 pt-6 sm:px-7">
      <Link href="/" className="text-[13px]">
        ← Dashboard
      </Link>

      <section className="panel flex flex-wrap items-end justify-between gap-4 p-5">
        <div className="flex items-end gap-5">
          <CardThumb src={cardImage(m)} player={m.player} size="lg" />
          <div>
          <p className="eyebrow">
            {m.sport} · {m.brand}
          </p>
          <h1 className="mt-1 text-[22px] font-bold">
            {m.player}{' '}
            {m.rookie_flag && <span className="badge bg-warn/15 align-middle text-warn">RC</span>}
            {m.autograph_flag && <span className="badge ml-1 bg-link/15 align-middle text-link">AUTO</span>}
          </h1>
          <p className="text-muted">
            {m.year} {m.card_set} #{m.card_number}
            {m.parallel ? ` · ${m.parallel}` : ''}
            {m.print_run ? ` /${m.print_run}` : ''}
          </p>
          <CardEditForm
            cardId={m.id}
            player={m.player}
            year={m.year}
            cardNumber={m.card_number}
            setName={m.card_set}
            parallel={m.parallel}
            printRun={m.print_run}
            rookie={m.rookie_flag}
          />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <nav aria-label="Grade" className="flex flex-wrap gap-1">
            {[{ key: 'all', label: 'All grades', comp_count: detail.grades.reduce((s, g) => s + g.comp_count, 0) }, ...detail.grades].map((g) => (
              <Link
                key={g.key}
                href={href(g.key, window)}
                aria-current={activeGrade === g.key ? 'page' : undefined}
                className={`flex min-h-11 items-center rounded-md px-3 font-mono text-[12px] ${activeGrade === g.key ? 'bg-raised text-ink' : ''}`}
              >
                {g.label} <span className="ml-1.5 text-muted">{g.comp_count}</span>
              </Link>
            ))}
          </nav>
          <nav aria-label="Window" className="flex flex-wrap gap-1">
            {WINDOWS.map((w) => (
              <Link
                key={w}
                href={href(activeGrade, w)}
                aria-current={window === w ? 'page' : undefined}
                className={`flex min-h-11 items-center rounded-md px-3 font-mono text-[12px] uppercase ${window === w ? 'bg-raised text-ink' : ''}`}
              >
                {w}
              </Link>
            ))}
          </nav>
        </div>
      </section>

      <section aria-label="Valuation" className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
        <Kpi label={`Estimate · ${v.grade}`} value={money(v.estimated_price)} sub={v.last_sale_at ? `Last sale ${longDate(v.last_sale_at)}` : 'No sales yet'} />
        <Kpi label="Range (IQR)" value={<span className="text-[22px]">{`${money(v.low_estimate, { whole: true })} – ${money(v.high_estimate, { whole: true })}`}</span>} />
        <Kpi label="Confidence" value={conf.label} valueClass={conf.cls} sub={`${Math.round(v.confidence_score * 100)} / 100`} />
        <Kpi label={`Comps · ${window}`} value={detail.stats.count} sub={`Median ${money(detail.stats.median_price)} · avg ${money(detail.stats.average_price)}`} />
      </section>

      <MarketTrend cardId={m.id} grade={activeGrade} />

      <div className="flex flex-wrap items-start gap-5">
        <section className="panel flex min-w-0 flex-1 flex-col gap-3 p-5" aria-label="How this was valued">
          <h2 className="panel-title">How this was valued</h2>
          <p className="text-[13px] leading-relaxed text-ink">{v.explanation}</p>
          <div className="flex flex-wrap gap-1.5">
            {v.reason_codes.map((r) => (
              <span key={r} className="badge bg-raised font-mono text-muted">
                {r}
              </span>
            ))}
          </div>
          <div className="mt-2 border-t border-line pt-3">
            <p className="eyebrow mb-2">Raw vs PSA 10 (all time)</p>
            <div className="grid grid-cols-3 gap-2 font-mono text-[12px]">
              <div className="tile">
                <span className="text-muted">Raw</span>
                <br />
                <b className="text-[15px]">{money(detail.comparison.raw_median, { whole: true })}</b>
                <span className="block text-muted">{detail.comparison.raw_count} sales</span>
              </div>
              <div className="tile">
                <span className="text-muted">PSA 10</span>
                <br />
                <b className="text-[15px]">{money(detail.comparison.psa10_median, { whole: true })}</b>
                <span className="block text-muted">{detail.comparison.psa10_count} sales</span>
              </div>
              <div className="tile">
                <span className="text-muted">Premium</span>
                <br />
                <b className="text-[15px]">{detail.comparison.grading_premium ? `${detail.comparison.grading_premium}×` : '—'}</b>
              </div>
            </div>
          </div>
        </section>
      </div>

      <EbayMarketPanel cardId={m.id} grade={activeGrade} player={m.player} />

      <AiPricePanel cardId={m.id} grade={activeGrade} />

    </main>
  );
}
