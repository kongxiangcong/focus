export function LibraryProgress({ label, value, max }: { label: string; value: number; max: number }) {
  const limit = Math.max(1, max), current = Math.max(0, Math.min(limit, value));
  return <div className="library-progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={current}><span style={{ transform: `scaleX(${current / limit})` }} /></div>;
}
