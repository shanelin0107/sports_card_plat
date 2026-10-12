'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { api } from '@/lib/client-api';
import { longDate, money } from '@/lib/format';
import type { CardSearchResult, IngestionIssue, IngestionRun } from '@/lib/types';

import { CardPicker } from './CardPicker';

const TYPE_LABEL: Record<IngestionIssue['issue_type'], { label: string; cls: string; help: string }> = {
  unmatched: { label: 'Unmatched', cls: 'bg-warn/15 text-warn', help: 'No catalog card fits this listing.' },
  low_confidence: { label: 'Low confidence', cls: 'bg-link/15 text-link', help: 'A likely card was found but not certain enough to use automatically.' },
  parse_error: { label: 'Unreadable', cls: 'bg-down/15 text-down', help: 'Year, price or date could not be read from the listing.' },
};

export function ReviewQueue({ initialRuns }: { initialRuns: IngestionRun[] }) {
  const [status, setStatus] = useState<'open' | 'resolved' | 'dismissed'>('open');
  const [issues, setIssues] = useState<IngestionIssue[] | null>(null);
  const [runs, setRuns] = useState(initialRuns);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    setIssues(null);
    api<IngestionIssue[]>(`/internal/ingestion/issues?status=${status}`)
      .then(setIssues)
      .catch((e: Error) => setMsg(e.message));
  }, [status]);

  useEffect(load, [load]);

  async function runNow() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<IngestionRun>('/internal/ingestion/run?mode=daily', { method: 'POST' });
      setRuns((xs) => [r, ...xs].slice(0, 10));
      setMsg(`Run #${r.id}: fetched ${r.fetched_count}, promoted ${r.promoted_count}, ${r.low_confidence_count} low-confidence, ${r.parse_error_count} unreadable.`);
      load();
    } catch (e) {
      setMsg(`Run failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-start gap-5">
      <section className="panel min-w-0 flex-[999_1_560px]" aria-label="Review queue">
        <div className="panel-head flex-wrap">
          <h1 className="panel-title">Review queue</h1>
          <div role="tablist" aria-label="Filter" className="flex gap-1">
            {(['open', 'resolved', 'dismissed'] as const).map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={status === s}
                onClick={() => setStatus(s)}
                className={`min-h-11 rounded-md px-3 capitalize ${status === s ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        {issues === null ? (
          <p className="p-5 text-muted">Loading…</p>
        ) : issues.length === 0 ? (
          <p className="p-5 text-muted">{status === 'open' ? 'Nothing to review.' : `No ${status} items.`}</p>
        ) : (
          <ul className="divide-y divide-line">
            {issues.map((i) => (
              <IssueRow key={i.id} issue={i} onDone={() => setIssues((xs) => (xs ?? []).filter((x) => x.id !== i.id))} />
            ))}
          </ul>
        )}
      </section>

      <aside className="panel flex min-w-0 flex-[1_1_320px] flex-col gap-3 p-[18px]" aria-label="Ingestion runs">
        <h2 className="panel-title">Runs</h2>
        <button className="btn-primary" onClick={runNow} disabled={busy}>
          {busy ? 'Running…' : 'Run ingest now'}
        </button>
        {msg && (
          <p className="text-[12px] text-muted" role="status">
            {msg}
          </p>
        )}
        <ul className="space-y-2 font-mono text-[12px]">
          {runs.map((r) => (
            <li key={r.id} className="tile flex justify-between gap-2">
              <span>
                #{r.id} {r.mode} <span className="text-muted">{longDate(r.started_at)}</span>
              </span>
              <span className={r.status === 'failed' ? 'text-down' : r.status === 'completed' ? 'text-up' : 'text-warn'}>
                {r.status === 'completed' ? `+${r.promoted_count}` : r.status}
              </span>
            </li>
          ))}
          {runs.length === 0 && <li className="text-muted">No runs yet.</li>}
        </ul>
      </aside>
    </div>
  );
}

function IssueRow({ issue, onDone }: { issue: IngestionIssue; onDone: () => void }) {
  const [matching, setMatching] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const t = TYPE_LABEL[issue.issue_type];
  const d = issue.details ?? {};
  const canMatch = issue.status === 'open' && issue.normalized_sale_id !== null;

  async function act(path: string, body?: object) {
    setBusy(true);
    setErr(null);
    try {
      await api(`/internal/ingestion/issues/${issue.id}/${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-3 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <span className={`badge ${t.cls}`}>{t.label}</span>
          <p className="mt-1.5 break-words font-bold">“{d.title ?? issue.source_listing_id}”</p>
          <p className="num mt-0.5 text-[12px] text-muted">
            {d.price !== undefined ? money(d.price) : ''} {d.grade ? `· ${d.grade === 'Raw' ? 'Raw' : `grade ${d.grade}`}` : ''}{' '}
            {d.sold_at ? `· sold ${longDate(d.sold_at)}` : ''} {d.confidence !== undefined ? `· confidence ${Math.round(d.confidence * 100)}%` : ''}
            {d.reason ? `· ${d.reason.replaceAll('_', ' ')}` : ''}
          </p>
          <p className="mt-0.5 text-[12px] text-muted">{t.help}</p>
          {issue.resolution_card_id && (
            <Link href={`/cards/${issue.resolution_card_id}`} className="text-[12px] text-link">
              Matched to card #{issue.resolution_card_id} →
            </Link>
          )}
        </div>
        {issue.status === 'open' && (
          <div className="flex flex-wrap gap-2">
            {issue.issue_type === 'low_confidence' && d.suggested_card_id && (
              <button className="btn-primary" disabled={busy} onClick={() => act('resolve', { card_id: d.suggested_card_id })}>
                Accept suggestion
              </button>
            )}
            {canMatch && (
              <button className="btn-ghost" onClick={() => setMatching((m) => !m)} aria-expanded={matching}>
                Match to card
              </button>
            )}
            <button className="btn-ghost" disabled={busy} onClick={() => act('dismiss')}>
              Dismiss
            </button>
          </div>
        )}
      </div>
      {matching && (
        <CardPicker
          label="Which card is this sale for?"
          initialQuery={(d.title ?? '').replace(/psa\s*\d+/i, '').replace(/#/g, '').trim()}
          onPick={(c: CardSearchResult) => act('resolve', { card_id: c.id })}
        />
      )}
      {err && <p className="text-[13px] text-down">{err}</p>}
    </li>
  );
}
