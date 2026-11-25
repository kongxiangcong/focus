import type { BlogStatus, IngestionItem, ProcessingBatch } from "@focus/reader-contracts";
import { LibraryProgress } from "./LibraryProgress";
import { ingestionFormat } from "./ingestion-format";

type Item = ProcessingBatch["items"][number] | IngestionItem;

export function UploadProgress({ item, blog }: { item?: Item; blog?: BlogStatus }) {
  const parsing = item && ("ingestionStatus" in item ? item.ingestionStatus : item.status);
  let label: string;
  let active = false;
  let percent: number | undefined;
  if (item && parsing && parsing !== "completed") {
    const progress = item.parserProgress;
    if (["confirmed", "awaiting_confirmation"].includes(parsing) || progress?.status === "queued" && parsing === "processing") {
      label = "排队中";
    } else if (parsing === "processing") {
      active = true;
      percent = typeof progress?.percent === "number" && Number.isFinite(progress.percent)
        ? Math.max(0, Math.min(100, Math.round(progress.percent))) : undefined;
      label = percent === undefined ? "解析中" : `解析中 ${percent}%`;
    } else {
      label = "解析未完成";
    }
  } else if (blog?.executing || blog?.runStatus === "running") {
    label = "正在生成博客";
    active = true;
  } else if (blog?.artifacts?.html?.status === "completed") {
    label = "博客已完成";
  } else if (blog?.error || ["failed", "cancelled", "interrupted"].includes(blog?.runStatus ?? "") ||
             item && ["failed", "partial", "cancelled"].includes(item.status)) {
    label = "博客生成未完成";
  } else if (item && item.status !== "completed" && ingestionFormat(item.fileName) !== "Markdown") {
    label = "等待生成博客";
    active = true;
  } else {
    return null;
  }
  return <div className="upload-progress"><small>{label}</small>
    {active && (percent === undefined ? <progress aria-label={label} /> :
      <LibraryProgress label={`${item?.fileName} 解析进度`} value={percent} max={100} />)}
  </div>;
}
