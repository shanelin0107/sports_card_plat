export function ErrorState({ title = 'Backend unreachable', detail }: { title?: string; detail?: string }) {
  return (
    <div className="panel border-warn/40 p-5">
      <p className="font-bold text-warn">{title}</p>
      <p className="mt-1 text-[13px] text-muted">
        {detail ?? 'The API did not respond. Check that the backend is running and API_BASE_URL points at it.'}
      </p>
    </div>
  );
}
