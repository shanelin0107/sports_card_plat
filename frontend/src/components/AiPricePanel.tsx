'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money } from '@/lib/format';

type PriceItem = {
  price: number;
  date?: string;
  grade?: string;
  title: string;
  url: string;
  source: string;
  exact_match: boolean;
  note?: string;
  saved_comp_id?: number;
};

type Research = {
  id: number;
  card_id: number | null;
  query: string;
  status: 'running' | 'completed' | 'failed';
  model: string | null;
  error_message: string | null;
  searches_used: number;
  created_at: string;
  completed_at: string | null;
  result: {
    identified_card: { description: string; lookalikes?: string[] };
    identification_confidence: 'high' | 'medium' | 'low';
    sold: PriceItem[];
    active: PriceItem[];
    unverified?: (PriceItem & { dropped_reason: string })[];
    estimate?: { low?: number; mid?: number; high?: number; grade?: string; basis?: string };
    summary: string;
    caveats?: string[];
  } | null;
};

const CONF: Record<string, string> = { high: 'bg-up/15 text-up', medium: 'bg-link/15 text-link', low: 'bg-warn/15 text-warn' };

/** "psa10" -> "PSA 10", "raw" -> "Raw", "all"/undefined -> undefined */
export function gradeText(g?: string | null): string | undefined {
  if (!g || g === 'all') return undefined;
  if (g === 'raw') return 'Raw';
  const m = g.match(/^([a-z]+)(.+)$/i);
  return m ? `${m[1].toUpperCase()} ${m[2]}` : g;
}

export function AiPricePanel({ cardId, query, grade }: { cardId?: number; query?: string; grade?: string }) {
  const router = useRouter();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [job, setJob] = useState<Research | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback((id: number) => {
    timer.current = setTimeout(async () => {
      try {
        const j = await api<Research>(`/ai/price-research/${id}`);
        setJob(j);
        if (j.status === 'running') poll(id);
      } catch (e) {
        setErr((e as Error).message);
      }
    }, 3000);
  }, []);

  useEffect(() => {
    api<{ enabled: boolean }>('/ai/status')
      .then((s) => setEnabled(s.enabled))
      .catch(() => setEnabled(false));
    if (cardId) {
      api<Research[]>(`/ai/price-research?card_id=${cardId}&limit=1`)
        .then((rs) => {
          if (rs[0]) {
            setJob(rs[0]);
            if (rs[0].status === 'running') poll(rs[0].id);
          }
        })
        .catch(() => {});
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [cardId, poll]);

  async function start() {
    setErr(null);
    try {
      const j = await api<Research>('/ai/price-research', {
        method: 'POST',
        body: JSON.stringify({ card_id: cardId ?? null, query: cardId ? null : query, grade: gradeText(grade) ?? null }),
      });
      setJob(j);
      poll(j.id);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function save(index: number) {
    if (!job) return;
    setSaving(index);
    setErr(null);
    try {
      const r = await api<{ sale_comp_id: number }>(`/ai/price-research/${job.id}/save-comp`, {
        method: 'POST',
        body: JSON.stringify({ index }),
      });
      setJob((j) => {
        if (!j?.result) return j;
        const sold = j.result.sold.map((s, i) => (i === index ? { ...s, saved_comp_id: r.sale_comp_id } : s));
        return { ...j, result: { ...j.result, sold } };
      });
      router.refresh(); // valuation, chart and comps table pick up the new sale
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(null);
    }
  }

  const running = job?.status === 'running';
  const r = job?.status === 'completed' ? job.result : null;

  return (
    <section className="panel" aria-label="AI price check">
      <div className="panel-head flex-wrap">
        <div>
          <h2 className="panel-title">AI price check</h2>
          <p className="text-[12px] text-muted">Claude searches the web for recent sales and live listings of this exact card. Nothing is saved until you confirm it.</p>
        </div>
        {enabled && (
          <button className="btn-primary" onClick={start} disabled={running}>
            {running ? 'Researching…' : job ? 'Run again' : 'Ask AI for prices'}
          </button>
        )}
      </div>

      <div className="space-y-4 p-5">
        {enabled === false && (
          <p className="text-[13px] text-muted">
            Turned off. Add <code className="font-mono text-ink">ANTHROPIC_API_KEY=…</code> to the project’s <code className="font-mono text-ink">.env</code> and restart the backend.
          </p>
        )}
        {err && <p className="text-[13px] text-down">{err}</p>}
        {running && (
          <p className="text-[13px] text-muted" role="status">
            Searching sold listings, price guides and checklists… this usually takes 30–90 seconds.
          </p>
        )}
        {job?.status === 'failed' && <p className="text-[13px] text-down">Research failed: {job.error_message}</p>}
        {!job && enabled && <p className="text-[13px] text-muted">No research yet for this card.</p>}

        {r && job && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="eyebrow">Identified as</p>
                <p className="mt-1 font-bold">{r.identified_card.description}</p>
                {r.identified_card.lookalikes && r.identified_card.lookalikes.length > 0 && (
                  <p className="mt-1 text-[12px] text-warn">Don’t confuse with: {r.identified_card.lookalikes.join(' · ')}</p>
                )}
              </div>
              <span className={`badge ${CONF[r.identification_confidence] ?? ''}`}>{r.identification_confidence} confidence</span>
            </div>

            {r.estimate && (r.estimate.mid || r.estimate.low) && (
              <div className="grid grid-cols-3 gap-2 font-mono text-[12px]">
                <div className="tile">
                  <span className="text-muted">Low</span>
                  <br />
                  <b className="text-[16px]">{money(r.estimate.low)}</b>
                </div>
                <div className="tile">
                  <span className="text-muted">AI estimate{r.estimate.grade ? ` · ${r.estimate.grade}` : ''}</span>
                  <br />
                  <b className="text-[16px] text-up">{money(r.estimate.mid)}</b>
                </div>
                <div className="tile">
                  <span className="text-muted">High</span>
                  <br />
                  <b className="text-[16px]">{money(r.estimate.high)}</b>
                </div>
              </div>
            )}
            <p className="text-[13px] leading-relaxed">{r.summary}</p>

            <PriceTable
              title={`Sold (${r.sold.length})`}
              empty="No verified sales found."
              items={r.sold}
              action={(it, i) =>
                !cardId ? null : it.saved_comp_id ? (
                  <span className="text-[12px] text-up">Saved</span>
                ) : !it.exact_match ? (
                  <span className="text-[12px] text-muted">reference only</span>
                ) : !it.date ? (
                  <span className="text-[12px] text-muted">no date</span>
                ) : (
                  <button className="btn-ghost min-h-9 px-3 text-[12px]" disabled={saving === i} onClick={() => save(i)}>
                    {saving === i ? 'Saving…' : 'Save as comp'}
                  </button>
                )
              }
            />
            <PriceTable title={`Listed now (${r.active.length})`} empty="No live listings found." items={r.active} />

            {(r.caveats?.length || r.unverified?.length) ? (
              <ul className="list-disc space-y-1 pl-5 text-[12px] text-muted">
                {r.caveats?.map((c) => <li key={c}>{c}</li>)}
                {r.unverified && r.unverified.length > 0 && (
                  <li>{r.unverified.length} price(s) the model mentioned were discarded because their source page was never actually retrieved.</li>
                )}
              </ul>
            ) : null}
            <p className="font-mono text-[11px] text-muted">
              {longDate(job.completed_at)} · {job.searches_used} searches · {job.model}
            </p>
          </>
        )}
      </div>
    </section>
  );
}

function PriceTable({
  title,
  empty,
  items,
  action,
}: {
  title: string;
  empty: string;
  items: PriceItem[];
  action?: (it: PriceItem, i: number) => React.ReactNode;
}) {
  return (
    <div>
      <p className="eyebrow mb-2">{title}</p>
      {items.length === 0 ? (
        <p className="text-[13px] text-muted">{empty}</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="w-full min-w-[640px] border-collapse text-[12px]">
            <tbody>
              {items.map((it, i) => (
                <tr key={`${it.url}-${i}`} className="border-t border-line first:border-0">
                  <td className="py-2 pl-3 pr-2 font-mono text-muted">{it.date ?? '—'}</td>
                  <td className="px-2">
                    <a href={it.url} target="_blank" rel="noopener noreferrer nofollow" className="text-ink hover:text-link">
                      {it.title}
                    </a>
                    <span className="block text-muted">
                      {it.source}
                      {it.note ? ` · ${it.note}` : ''}
                    </span>
                  </td>
                  <td className="px-2">
                    {it.exact_match ? (
                      <span className="badge bg-up/15 text-up">exact</span>
                    ) : (
                      <span className="badge bg-warn/15 text-warn">similar</span>
                    )}
                  </td>
                  <td className="px-2 font-mono">{it.grade ?? '—'}</td>
                  <td className="px-2 text-right font-mono">{money(it.price)}</td>
                  <td className="py-2 pl-2 pr-3 text-right">{action?.(it, i)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
