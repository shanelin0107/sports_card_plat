import { money, shortDate } from '@/lib/format';

type Point = { date: string; value: number };

/** Dependency-free SVG line chart that renders on the server or client. */
export function PriceChart({ points, height = 140, label }: { points: Point[]; height?: number; label: string }) {
  if (points.length === 0) {
    return <div className="flex h-[120px] items-center justify-center rounded-md bg-base text-[13px] text-muted">No sales in this window.</div>;
  }
  const W = 340;
  const padL = 4;
  const padR = 4;
  const padT = 10;
  const padB = 22;
  const vals = points.map((p) => p.value);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const lo = min === max ? min * 0.9 : min - (max - min) * 0.15;
  const hi = min === max ? max * 1.1 : max + (max - min) * 0.15;
  const x = (i: number) => (points.length === 1 ? W / 2 : padL + (i / (points.length - 1)) * (W - padL - padR));
  const y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * (height - padT - padB);
  const line = points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ');
  const desc = `${label}: ${points.length} data points from ${money(min)} to ${money(max)}`;

  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} role="img" aria-label={desc}>
      {[0, 0.5, 1].map((f) => (
        <line key={f} x1="0" x2={W} y1={padT + f * (height - padT - padB)} y2={padT + f * (height - padT - padB)} stroke="#1E2A36" />
      ))}
      <text x={W - 2} y={padT - 2} textAnchor="end" fontSize="10" fill="#9FB3C8" fontFamily="JetBrains Mono">
        {money(hi, { whole: true })}
      </text>
      <text x={W - 2} y={height - padB - 3} textAnchor="end" fontSize="10" fill="#9FB3C8" fontFamily="JetBrains Mono">
        {money(lo, { whole: true })}
      </text>
      {points.length > 1 && <polyline points={line} fill="none" stroke="#3DDC97" strokeWidth="2.5" strokeLinejoin="round" />}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(p.value)}
          r="4"
          fill={i === points.length - 1 ? '#3DDC97' : '#0B0F14'}
          stroke="#3DDC97"
          strokeWidth="2"
        >
          <title>{`${p.date}: ${money(p.value)}`}</title>
        </circle>
      ))}
      <text x={x(0)} y={height - 6} textAnchor={points.length === 1 ? 'middle' : 'start'} fontSize="10" fill="#9FB3C8" fontFamily="JetBrains Mono">
        {shortDate(points[0].date)}
      </text>
      {points.length > 1 && (
        <text x={x(points.length - 1)} y={height - 6} textAnchor="end" fontSize="10" fill="#9FB3C8" fontFamily="JetBrains Mono">
          {shortDate(points[points.length - 1].date)}
        </text>
      )}
    </svg>
  );
}
