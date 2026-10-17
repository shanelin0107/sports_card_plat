'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { api } from '@/lib/client-api';
import { confidenceLabel, money, pct, signedMoney, tone } from '@/lib/format';
import { gradeParam } from '@/lib/grade';
import { holdingImage } from '@/lib/images';
import type { CardDetail, Holding, SalesHistory } from '@/lib/types';

import { CardThumb } from './CardThumb';
import { PriceChart } from './PriceChart';
import { Sparkline } from './Sparkline';

export function HoldingsBoard({ holdings }: { holdings: Holding[] }) {
  const ranked = [...holdings].sort((a, b) => (b.estimated_value ?? 0) - (a.estimated_value ?? 0));
  const [selectedId, setSelectedId] = useState<number | null>(ranked[0]?.id ?? null);
  const selected = holdings.find((h) => h.id === selectedId) ?? null;

  return (
    <div className="flex flex-wrap items-start gap-5">
      <section aria-label="Holdings" className="panel min-w-0 flex-[999_1_560px]">
        <div className="panel-head">
          <h2 className="panel-title">Holdings</h2>
          <Link href="/search" className="btn-ghost text-ink">
            + Add card
          </Link>
        </div>
        {holdings.length === 0 ? (
          <p className="p-5 text-muted">
            No cards yet. <Link href="/search" className="text-link">Search sold prices to add your first card →</Link>
          </p>
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-[13px]">
              <thead>
                <tr>
                  <th className="th pl-5">Card</th>
                  <th className="th">Grade</th>
                  <th className="th text-right">Cost</th>
                  <th className="th text-right">Est.</th>
                  <th className="th">Trend</th>
                  <th className="th pr-5 text-right">P&amp;L</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {ranked.map((h) => {
                  const active = h.id === selectedId;
                  return (
                    <tr
                      key={h.id}
                      className={`border-t border-line ${active ? 'bg-raised' : 'hover:bg-raised/50'}`}
                    >
                      <td className="td pl-5 font-sans">
                        <button
                          type="button"
                          onClick={() => setSelectedId(h.id)}
                          aria-pressed={active}
                          className="flex min-h-11 items-center gap-3 text-left"
                        >
                          <CardThumb src={holdingImage(h)} player={h.player} />
                          <span>
                            <b className="text-ink">{h.player}</b>{' '}
                            {h.rookie_flag && <span className="badge bg-warn/15 text-warn">RC</span>}
                            <br />
                            <span className="text-[12px] text-muted">
                              {h.year} {h.card_set} #{h.card_number}
                              {h.parallel && h.parallel !== 'Base' ? ` · ${h.parallel}` : ''}
                              {h.quantity > 1 ? ` · ×${h.quantity}` : ''}
                            </span>
                          </span>
                        </button>
                      </td>
                      <td className="td">{h.grade_label}</td>
                      <td className="td text-right">{money(h.purchase_price * h.quantity)}</td>
                      <td className="td text-right text-ink">
                        {money(h.estimated_value)}
                        <span className="block text-[11px] text-muted">
                          {h.sales_30d > 0 ? `30d ${money(h.median_30d, { whole: true })} · ${h.sales_30d} sold` : '0 sold 30d'}
                        </span>
                      </td>
                      <td className="td">
                        <Sparkline values={h.spark} />
                      </td>
                      <td className={`td pr-5 text-right ${tone(h.unrealized_pnl)}`}>
                        {signedMoney(h.unrealized_pnl)}
                        <br />
                        <span className="text-[11px]">{pct(h.unrealized_pnl_pct)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {selected && <SelectedCard key={selected.id} holding={selected} />}
    </div>
  );
}

function SelectedCard({ holding }: { holding: Holding }) {
  const [detail, setDetail] = useState<CardDetail | null>(null);
  const [history, setHistory] = useState<SalesHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const g = gradeParam(holding);
    Promise.all([
      api<CardDetail>(`/cards/${holding.card_id}?grade=${g}&window=30d`),
      api<SalesHistory>(`/cards/${holding.card_id}/sales-history?grade=${g}&window=all`),
    ])
      .then(([d, h]) => {
        setDetail(d);
        setHistory(h);
      })
      .catch((e: Error) => setError(e.message));
  }, [holding]);

  const v = detail?.valuation;
  const conf = confidenceLabel(v?.confidence_score);
  return (
    <section aria-label="Selected card" className="panel flex min-w-0 flex-[1_1_380px] flex-col gap-3.5 p-[18px]">
      <div className="flex items-start gap-3.5">
        <CardThumb src={holdingImage(holding)} player={holding.player} size="md" />
        <div>
          <p className="eyebrow">Valuation · {v?.window_used ?? '30d'} window</p>
          <h2 className="mt-1 text-[18px] font-bold">
            {holding.player?.split(' ').slice(-1)[0]} {holding.card_set?.replace(/^(Topps|Panini) /, '')}
            {holding.parallel && holding.parallel !== 'Base' ? ` ${holding.parallel}` : ''} {holding.grade_label}
          </h2>
        </div>
      </div>
      {error && <p className="text-[13px] text-warn">Couldn’t load details: {error}</p>}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="num text-[34px] font-bold">{money(v?.estimated_price ?? holding.estimated_unit_price, { whole: true })}</span>
        <span className="num text-muted">
          range {money(v?.low_estimate, { whole: true })} – {money(v?.high_estimate, { whole: true })}
        </span>
      </div>
      <PriceChart
        label={`${holding.grade_label} sold prices`}
        points={(history?.price_series ?? []).map((p) => ({ date: p.date, value: p.median_price ?? 0 }))}
      />
      <div className="grid grid-cols-3 gap-2 text-[12px]">
        <div className="tile">
          <span className="text-muted">Comps</span>
          <br />
          <b className="num text-[15px]">{v ? v.exact_comp_count : '—'}</b>
        </div>
        <div className="tile">
          <span className="text-muted">Confidence</span>
          <br />
          <b className={`num text-[15px] ${conf.cls}`}>{conf.label}</b>
        </div>
        <div className="tile">
          <span className="text-muted">Method</span>
          <br />
          <b className="text-[13px]">{v ? (v.method === 'exact_recent_comps_median' ? 'Median' : v.method === 'no_data' ? 'No data' : 'Few sales') : '—'}</b>
        </div>
      </div>
      {v && (
        <p className="text-[12px] leading-relaxed text-muted">
          {v.explanation} Reason codes: {v.reason_codes.join(' · ')}.
        </p>
      )}
      <Link href={`/cards/${holding.card_id}?grade=${gradeParam(holding)}`} className="text-[13px] text-link hover:text-ink">
        Full comp history →
      </Link>
    </section>
  );
}
