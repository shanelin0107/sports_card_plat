/** Sports offered when adding a card. Keep "Other" last. */
export const SPORTS = ['Baseball', 'Basketball', 'Football', 'Hockey', 'Soccer', 'F1', 'Other'] as const;

/** Map how listings and titles name a sport onto our list ("Formula 1 Racing" -> "F1"). */
export function normalizeSport(s: string | null | undefined): string | null {
  if (!s) return null;
  if (/\b(f1|formula\s*(1|one))\b/i.test(s)) return 'F1';
  const hit = SPORTS.find((x) => x.toLowerCase() === s.trim().toLowerCase());
  return hit ?? null;
}
