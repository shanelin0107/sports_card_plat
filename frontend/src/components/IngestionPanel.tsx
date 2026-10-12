'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import { api } from '@/lib/client-api';
import { longDate } from '@/lib/format';
import type { IngestionRun, SourceHealth } from '@/lib/types';

export function IngestionPanel({ health }: { health: SourceHealth | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [, startTransition] = useTransition();
  const src = health?.sources[0];
  const issues = health?.open_issues ?? { unmatched: 0, low_confidence: 0, parse_error: 0 };
  const healthy = src ? src.healthy : health?.last_run?.status !== 'failed';

  async function run() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<IngestionRun>('/internal/ingestion/run?mode=daily', { method: 'POST' });
      setMsg(`Fetched ${r.fetched_count}, promoted ${r.promoted_count}.`);
      startTransition(() => router.refresh());
    } catch (e) {
      setMsg(`Run failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Ingestion health" className="panel flex min-w-0 flex-[1_1_320px] flex-col gap-3 px-[18px] py-4">
      <h2 className="panel-title">Ingestion · eBay feed</h2>
      <div className="flex items-center gap-2 text-[13px]">
        <span className={`h-2 w-2 rounded-full ${health?.last_run ? (healthy ? 'bg-up' : 'bg-down') : 'bg-muted'}`} aria-hidden="true" />
        {health?.last_run
          ? `${healthy ? 'Source healthy' : 'Last run failed'} · last run ${longDate(health.last_run.started_at)}`
          : 'No runs yet'}
      </div>
      <div className="grid grid-cols-3 gap-2 font-mono">
        <div className="tile">
          <span className="text-[11px] text-muted">Promoted 7d</span>
          <br />
          <b className="text-[18px]">{src?.promoted_last_7d ?? 0}</b>
        </div>
        <div className="tile">
          <span className="text-[11px] text-muted">Low conf.</span>
          <br />
          <b className={`text-[18px] ${issues.low_confidence ? 'text-warn' : ''}`}>{issues.low_confidence}</b>
        </div>
        <div className="tile">
          <span className="text-[11px] text-muted">Unmatched</span>
          <br />
          <b className={`text-[18px] ${issues.unmatched + issues.parse_error ? 'text-warn' : ''}`}>{issues.unmatched + issues.parse_error}</b>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-ghost" onClick={run} disabled={busy}>
          {busy ? 'Running…' : 'Run ingest now'}
        </button>
        <Link href="/review" className="text-[13px] text-link hover:text-ink">
          Review queue →
        </Link>
      </div>
      {msg && (
        <p className="text-[12px] text-muted" role="status">
          {msg}
        </p>
      )}
    </section>
  );
}
