import type { SourceStatus } from "./source-status";

export function BatteryProgress({ label, progress }: { label: string; progress: SourceStatus["progress"] }) {
  const { completed, total } = progress;
  const ratio = total > 0 ? completed / total : 0;
  const level = ratio === 0 ? "empty" : ratio <= 0.2 ? "low" : ratio < 0.6 ? "mid" : ratio < 1 ? "high" : "full";
  const text = total > 0 ? `${completed}/${total} 段 (${Math.floor(completed * 100 / total)}%)` : null;

  return <div className="library-battery" data-level={level}
    role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total || 100}
    aria-valuenow={completed} aria-valuetext={text ?? "尚无精读计划"}
    title={text ? `精读进度：${text}` : "尚无精读计划"}>
    <span className="library-battery__outline" aria-hidden="true">
      {completed > 0 && <span className="library-battery__fill" style={{ transform: `scaleX(${ratio})` }} />}
    </span>
    {text && <small aria-hidden="true">{text}</small>}
  </div>;
}
