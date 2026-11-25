import { UploadProgress } from "./UploadProgress";
import type { IngestionItem, LibrarySource, LibraryTopic, ProcessingBatch } from "@focus/reader-contracts";
import { UNFILED } from "./topic-view";
import { ingestionFormat } from "./ingestion-format";

export type IngestionRowsProps = {
  sources: readonly LibrarySource[]; topics: readonly LibraryTopic[]; topic: string;
  taskInbox: readonly IngestionItem[]; taskBatches: readonly ProcessingBatch[];
  statusText: Record<IngestionItem["status"], string>; itemStatusText: Record<ProcessingBatch["items"][number]["status"], string>;
  busy: string; canContinue: boolean; canControl: boolean; continueInbox: (item: IngestionItem) => void;
  controlBatch: (batchId: string, action: "retry-item", itemId: string) => Promise<void>; onTasks: () => void;
};
export function IngestionRows({ sources, topics, topic, taskInbox, taskBatches, statusText, itemStatusText, busy, canContinue, canControl, continueInbox, controlBatch, onTasks }: IngestionRowsProps) {
  const pending = (item: { sourceId: string | null; status: string }) => !["completed", "deleted"].includes(item.status) && (!item.sourceId || !sources.some(s => s.sourceId === item.sourceId));
  const matchesTopic = (id: string | null, title?: string | null) => !topic || (topic === UNFILED ? !id && !title : id ? id === topic : !!title && topics.some(t => t.topicId === topic && t.title.trim().toLowerCase() === title.trim().toLowerCase()));
  const target = (id: string | null, title?: string | null) => title || topics.find(t => t.topicId === id)?.title || id;
  const rows = [
    ...taskInbox.filter(item => pending(item) && matchesTopic(item.topicId, item.topicTitle)).map(item => {
      const recoverable = !item.resubmitRisk && ["retry_waiting", "failed", "commit_conflict", "topic_attachment_pending", "interrupted", "cancelled"].includes(item.status);
      return { key: `inbox:${item.itemId}`, item, status: statusText[item.status], target: target(item.topicId, item.topicTitle), label: "继续", disabled: !!busy || !canContinue, recover: recoverable ? () => continueInbox(item) : undefined };
    }),
    ...taskBatches.flatMap(batch => batch.items.filter(item => pending(item) && matchesTopic(batch.topicId)).map(item => {
      const recoverable = !item.resubmitRisk && ["failed", "partial", "cancelled"].includes(item.status);
      return { key: `batch:${batch.batchId}:${item.itemId}`, item, status: `${itemStatusText[item.status]} · ${item.ingestionStatus === "completed" ? "解析完成" : "解析：" + (statusText[item.ingestionStatus as IngestionItem["status"]] ?? "待处理")}`, target: target(batch.topicId), label: "重试未完成步骤", disabled: !!busy || !!batch.executing || !canControl, recover: recoverable ? () => void controlBatch(batch.batchId, "retry-item", item.itemId) : undefined };
    })),
  ];
  if (!rows.length) return null;
  return <section className="library-ingestions" aria-label="入库中">{rows.map(({ key, item, status, target, label, disabled, recover }) => {
    return <article className="library-ingestion" key={key} data-item-id={item.itemId}>
      <span className="source-badge">{ingestionFormat(item.fileName)}</span>
      <div className="library-source-main"><strong>{item.fileName}</strong><div className="library-source-meta"><span role="status">{item.parserBackend ? `${item.parserBackend === "local-mineru" ? "本地 MinerU" : "远端 MinerU API"} · ` : ""}{status}{item.selectionReason ? ` · ${item.selectionReason}` : ""}</span></div><small>{target ? `将加入 #${target}` : "不关联专题"}</small></div>
      <UploadProgress item={item} blog={("blog" in item && item.blog) || undefined} />
      {recover && <button disabled={disabled} onClick={recover}>{label}</button>}
      <button aria-label={`${item.fileName} 任务详情`} onClick={onTasks}>任务详情</button>
    </article>;
  })}</section>;
}
