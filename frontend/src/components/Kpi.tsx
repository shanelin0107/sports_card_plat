export function Kpi({ label, value, sub, valueClass = '' }: { label: string; value: React.ReactNode; sub?: React.ReactNode; valueClass?: string }) {
  return (
    <div className="panel px-[18px] py-4">
      <p className="eyebrow">{label}</p>
      <p className={`num mt-1.5 text-[28px] font-bold leading-tight sm:text-[30px] ${valueClass}`}>{value}</p>
      {sub && <p className="mt-1 text-[12px] text-muted">{sub}</p>}
    </div>
  );
}
