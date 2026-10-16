'use client';

import { DEFAULT_VIEW, GROUP_LABELS, SORT_LABELS, filterOptions, isFiltered, type GroupBy, type PnlFilter, type SortBy, type View } from '@/lib/collection-view';
import type { Holding } from '@/lib/types';

const PNL: { key: PnlFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'up', label: 'Up' },
  { key: 'down', label: 'Down' },
  { key: 'unpriced', label: 'No estimate' },
];

/** Search, filters, grouping and sorting for the collection table. */
export function CollectionToolbar({ items, view, onChange }: { items: Holding[]; view: View; onChange: (v: View) => void }) {
  const opts = filterOptions(items);
  const set = <K extends keyof View>(k: K, val: View[K]) => onChange({ ...view, [k]: val });
  const select = 'field h-10 min-w-0 py-0 text-[13px]';
  const filter = `${select} w-auto max-w-[220px]`; // the filter row sits on one line, not one per row

  return (
    <section className="panel space-y-3 p-4" aria-label="Filter and group">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={view.q}
          onChange={(e) => set('q', e.target.value)}
          placeholder="Search player, set, #, parallel, notes…"
          aria-label="Search your collection"
          className="field h-10 min-w-[200px] flex-[2_1_260px] text-[13px]"
        />
        <label className="flex flex-[1_1_170px] items-center gap-2 text-[12px] text-muted">
          Group by
          <select className={`${select} flex-1`} value={view.group} onChange={(e) => set('group', e.target.value as GroupBy)}>
            {(Object.keys(GROUP_LABELS) as GroupBy[]).map((g) => (
              <option key={g} value={g}>
                {GROUP_LABELS[g]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-[1_1_170px] items-center gap-2 text-[12px] text-muted">
          Sort
          <select className={`${select} flex-1`} value={view.sort} onChange={(e) => set('sort', e.target.value as SortBy)}>
            {(Object.keys(SORT_LABELS) as SortBy[]).map((s) => (
              <option key={s} value={s}>
                {SORT_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Grade" className={filter} value={view.grade} onChange={(e) => set('grade', e.target.value)}>
          <option value="all">All grades</option>
          <option value="raw">Raw only</option>
          <option value="graded">Graded only</option>
          {opts.grades.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
        {opts.sports.length > 1 && (
          <select aria-label="Sport" className={filter} value={view.sport} onChange={(e) => set('sport', e.target.value)}>
            <option value="all">All sports</option>
            {opts.sports.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        )}
        <select aria-label="Year" className={filter} value={view.year} onChange={(e) => set('year', e.target.value)}>
          <option value="all">All years</option>
          {opts.years.map((y) => (
            <option key={y}>{y}</option>
          ))}
        </select>
        <select aria-label="Set" className={filter} value={view.set} onChange={(e) => set('set', e.target.value)}>
          <option value="all">All sets</option>
          {opts.sets.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>

        <div role="group" aria-label="Profit and loss" className="flex rounded-md border border-edge">
          {PNL.map((p) => (
            <button
              key={p.key}
              type="button"
              aria-pressed={view.pnl === p.key}
              onClick={() => set('pnl', p.key)}
              className={`h-10 px-3 text-[12px] first:rounded-l-md last:rounded-r-md ${view.pnl === p.key ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          aria-pressed={view.rookie}
          onClick={() => set('rookie', !view.rookie)}
          className={`h-10 rounded-md border border-edge px-3 text-[12px] ${view.rookie ? 'bg-warn/15 text-warn' : 'text-muted hover:text-ink'}`}
        >
          RC only
        </button>

        {isFiltered(view) && (
          <button
            type="button"
            onClick={() => onChange({ ...DEFAULT_VIEW, group: view.group, sort: view.sort })}
            className="h-10 px-2 text-[12px] text-link hover:text-ink"
          >
            Clear filters
          </button>
        )}
      </div>
    </section>
  );
}
