'use client';

import { useState } from 'react';

import { api } from '@/lib/client-api';

export type SaleRow = { date: string; price: string; shipping: string; grade: string; url: string };

const GRADE_OPTIONS = ['Raw', 'PSA 10', 'PSA 9', 'PSA 8', 'PSA 7', 'BGS 10', 'BGS 9.5', 'BGS 9', 'SGC 10', 'SGC 9.5', 'SGC 9', 'CGC 10', 'CGC 9.5'];
const MONTHS: Record<string, number> = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

/** Today as YYYY-MM-DD in the user's own time zone (toISOString() is UTC and can be a day off). */
export function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// The date starts as today: Safari shows today's date greyed out in an EMPTY date box,
// so a blank default looked filled in but was never saved.
export const emptyRow = (grade = 'Raw'): SaleRow => ({ date: localToday(), price: '', shipping: '', grade, url: '' });

function isoDate(s: string): string | null {
  const t = s.trim();
  let m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/); // US m/d/y
  if (m) {
    const y = m[3].length === 2 ? `20${m[3]}` : m[3];
    return `${y}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
  }
  m = t.match(/^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$/); // Oct 1, 2026
  if (m && MONTHS[m[1].toLowerCase()]) return `${m[3]}-${String(MONTHS[m[1].toLowerCase()]).padStart(2, '0')}-${m[2].padStart(2, '0')}`;
  m = t.match(/^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$/); // 1 Oct 2026
  if (m && MONTHS[m[2].toLowerCase()]) return `${m[3]}-${String(MONTHS[m[2].toLowerCase()]).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  return null;
}

function normGrade(s: string): string | null {
  const t = s.trim();
  if (/^raw$|ungraded/i.test(t)) return 'Raw';
  const m = t.match(/\b(psa|bgs|sgc|cgc)\s*-?\s*(10|[1-9](?:\.5)?)\b/i);
  return m ? `${m[1].toUpperCase()} ${m[2]}` : null;
}

const DATE_RE = /\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\/\d{1,2}\/\d{2,4}|[A-Za-z]{3}[a-z]*\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3}[a-z]*\.?\s+\d{4})\b/;

/** Parse rows pasted from Excel / Google Sheets (tab-separated) or free text like 130point lines. */
export function parsePasted(text: string, defaultGrade: string): SaleRow[] {
  const rows: SaleRow[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const row = { ...emptyRow(defaultGrade), date: '' };
    const prices: string[] = [];
    if (line.includes('\t')) {
      for (const raw of line.split('\t')) {
        const c = raw.trim();
        if (!c) continue;
        if (/^https?:\/\//i.test(c)) row.url = c;
        else if (!row.date && isoDate(c)) row.date = isoDate(c)!;
        else if (normGrade(c)) row.grade = normGrade(c)!;
        else if (/^\$?\s*\d[\d,]*(\.\d{1,2})?$/.test(c)) prices.push(c.replace(/[$,\s]/g, ''));
      }
    } else {
      let rest = line;
      const url = rest.match(/https?:\/\/\S+/i);
      if (url) {
        row.url = url[0];
        rest = rest.replace(url[0], ' ');
      }
      const d = rest.match(DATE_RE);
      if (d && isoDate(d[1])) {
        row.date = isoDate(d[1])!;
        rest = rest.replace(d[0], ' ');
      }
      const g = normGrade(rest);
      if (g) row.grade = g;
      // free text: only amounts written with "$" count as prices
      for (const m of rest.matchAll(/\$\s?(\d[\d,]*(?:\.\d{1,2})?)/g)) prices.push(m[1].replace(/,/g, ''));
    }
    if (prices[0]) row.price = prices[0];
    if (prices[1]) row.shipping = prices[1];
    if (row.price || row.date) rows.push(row.date ? row : { ...row, date: localToday() });
  }
  return rows;
}

export function validRows(rows: SaleRow[]) {
  return rows.filter((r) => r.price && Number(r.price) > 0).map((r) => (r.date ? r : { ...r, date: localToday() }));
}

/** Save rows as sales on a card. Returns how many were saved and any errors. */
export async function saveSales(cardId: number, rows: SaleRow[]): Promise<{ saved: number; errors: string[] }> {
  let saved = 0;
  const errors: string[] = [];
  for (const r of validRows(rows)) {
    try {
      await api(`/market/sales/${cardId}`, {
        method: 'POST',
        body: JSON.stringify({
          price: Number(r.price),
          shipping: r.shipping ? Number(r.shipping) : null,
          date: r.date,
          grade: r.grade,
          url: r.url.trim() || null,
        }),
      });
      saved += 1;
    } catch (e) {
      errors.push(`${r.date} ${r.price}: ${(e as Error).message}`);
    }
  }
  return { saved, errors };
}

/** Spreadsheet-like editor for recent sales. Paste from Excel/Sheets/130point anywhere in it. */
export function SalesGrid({
  rows,
  onChange,
  defaultGrade = 'Raw',
  soldSearchUrl,
}: {
  rows: SaleRow[];
  onChange: (rows: SaleRow[]) => void;
  defaultGrade?: string;
  soldSearchUrl?: string;
}) {
  const [pasteNote, setPasteNote] = useState<string | null>(null);
  const set = (i: number, k: keyof SaleRow, v: string) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  function onPaste(e: React.ClipboardEvent) {
    const text = e.clipboardData.getData('text');
    if (!text.includes('\n') && !text.includes('\t')) return; // single value: normal paste into the cell
    e.preventDefault();
    const parsed = parsePasted(text, defaultGrade);
    if (!parsed.length) {
      setPasteNote('Couldn’t find dates or prices in what you pasted.');
      return;
    }
    const kept = rows.filter((r) => r.price || r.url);
    onChange([...kept, ...parsed]);
    setPasteNote(`Pasted ${parsed.length} row${parsed.length > 1 ? 's' : ''}. Check the grades before saving.`);
  }

  const today = localToday();
  const cell = 'h-10 w-full min-w-0 rounded border border-edge bg-base px-2 font-mono text-[12px]';

  return (
    <div className="space-y-2" onPaste={onPaste}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12px] text-muted">
          Type sales, or copy rows from Excel / Google Sheets / 130point and paste here (date, price, shipping, grade, link — any order).
        </p>
        {soldSearchUrl && (
          <a href={soldSearchUrl} target="_blank" rel="noopener noreferrer" className="btn-ghost min-h-9 px-3 text-[12px]">
            eBay sold ↗
          </a>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[12px]">
          <thead>
            <tr className="text-left text-muted">
              <th className="px-1 pb-1 font-medium">Date</th>
              <th className="px-1 pb-1 font-medium">Sold for</th>
              <th className="px-1 pb-1 font-medium">Shipping</th>
              <th className="px-1 pb-1 font-medium">Grade</th>
              <th className="px-1 pb-1 font-medium">Link (optional)</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="p-1">
                  <input aria-label={`Sale ${i + 1} date`} type="date" max={today} value={r.date} onChange={(e) => set(i, 'date', e.target.value)} className={cell} />
                </td>
                <td className="p-1">
                  <input aria-label={`Sale ${i + 1} price`} type="number" min="0" step="0.01" placeholder="0.00" value={r.price} onChange={(e) => set(i, 'price', e.target.value)} className={cell} />
                </td>
                <td className="p-1">
                  <input aria-label={`Sale ${i + 1} shipping`} type="number" min="0" step="0.01" placeholder="0.00" value={r.shipping} onChange={(e) => set(i, 'shipping', e.target.value)} className={cell} />
                </td>
                <td className="p-1">
                  <select aria-label={`Sale ${i + 1} grade`} value={r.grade} onChange={(e) => set(i, 'grade', e.target.value)} className={cell}>
                    {[...new Set([r.grade, ...GRADE_OPTIONS])].map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                </td>
                <td className="p-1">
                  <input aria-label={`Sale ${i + 1} link`} placeholder="https://www.ebay.com/itm/…" value={r.url} onChange={(e) => set(i, 'url', e.target.value)} className={cell} />
                </td>
                <td className="p-1 text-center">
                  <button
                    type="button"
                    aria-label={`Remove sale ${i + 1}`}
                    onClick={() => onChange(rows.length > 1 ? rows.filter((_, j) => j !== i) : [emptyRow(defaultGrade)])}
                    className="h-10 w-8 rounded text-muted hover:bg-raised hover:text-down"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3">
        <button type="button" className="btn-ghost min-h-9 px-3 text-[12px]" onClick={() => onChange([...rows, emptyRow(defaultGrade)])}>
          + Add row
        </button>
        <span className="text-[12px] text-muted">{validRows(rows).length} sale(s) ready</span>
        {pasteNote && <span className="text-[12px] text-up">{pasteNote}</span>}
      </div>
    </div>
  );
}
