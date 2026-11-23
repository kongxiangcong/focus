import type { LibrarySource, LibraryTopic } from "@focus/reader-contracts";
import type { SourceStatus } from "./source-status";

export function TopicHead({ topic, sources, statusFor, disabled, reason, onRename, onDelete }: {
  topic: LibraryTopic; sources: readonly LibrarySource[]; statusFor: (source: LibrarySource) => SourceStatus;
  disabled: boolean; reason: string; onRename: () => void; onDelete: () => void;
}) {
  const members = topic.sourceIds.flatMap(id => { const source = sources.find(s => s.sourceId === id); return source ? [{ source, status: statusFor(source) }] : []; });
  return <section className="library-topic-head" aria-label="专题概览">
    <div className="library-topic-head-row"><p>已读完 <strong>{members.filter(m => m.status.phase === "completed").length}</strong> / {topic.sourceIds.length} 篇 · {members.filter(m => m.status.phase === "reading").length} 篇阅读中</p><button disabled={disabled} onClick={onRename}>重命名专题</button><button className="library-more-danger" disabled={disabled} onClick={onDelete}>删除专题</button></div>
    <ol className="library-topic-segments" aria-label="专题顺序与状态">{members.map(({ source, status }) => <li key={source.sourceId} data-tone={status.tone} title={`${source.displayTitle || source.title} · ${status.label}`}><span>{source.displayTitle || source.title} · {status.label}</span></li>)}</ol>
    <p className="library-view-hint">{reason || "顺序就是专题阅读顺序。拖动左侧序号，或在标题上按 Alt+↑/↓ 调整。"}</p>
  </section>;
}
