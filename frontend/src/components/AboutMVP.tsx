export default function AboutMVP() {
  return (
    <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
      <h2 className="mb-2 text-lg font-semibold">About this MVP</h2>
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
        <li>Single-user sports card intelligence MVP focused on core data flows.</li>
        <li>Data is seeded/demo-first for deterministic local verification.</li>
        <li>Live marketplace ingestion is intentionally deferred to a later phase.</li>
        <li>Valuation is deterministic and explainable (no LLM-based pricing logic).</li>
      </ul>
    </section>
  );
}
