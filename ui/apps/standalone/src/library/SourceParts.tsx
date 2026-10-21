import { LibraryProgress } from "./LibraryProgress";
import type { ReactNode } from "react";
import type { BlogStatus, LibrarySource, LibraryTopic } from "@focus/reader-contracts";
import { blogSummary, readingStatus, type SourceStatus, type primaryAction } from "./source-status";

export type SourceViewProps = {
  source: LibrarySource; status: SourceStatus; action: ReturnType<typeof primaryAction>; blog: BlogStatus | undefined;
  topics: readonly LibraryTopic[]; selected: boolean; expanded: boolean; candidate: boolean; menu: ReactNode;
  onOverview?: () => void; onBlog?: () => void;
  onSelect: () => void; onPrimary: () => void; onTopic: (id: string) => void;
};
export function sourceAttributes(source: LibrarySource) {
  return { "data-reading-status": readingStatus(source), "data-status": source.parseStatus !== "ready" ? "failed" : readingStatus(source) === "completed" ? "completed" : source.progress.completed > 0 ? "reading" : "unread" };
}
export function SourceKind({ source }: { source: LibrarySource }) {
  return <span className="source-badge" data-kind={source.kind}>{source.format ?? (source.kind === "paper" ? "PDF" : "HTML")}</span>;
}
export function SourceTitle({ source, expanded, onSelect, onPrimary, action }: SourceViewProps) {
  return <h3><button className="library-source-title" id={`source-title-${source.sourceId}`} title={source.title} aria-expanded={expanded} aria-controls={`source-details-${source.sourceId}`}
    onClick={event => { event.stopPropagation(); onSelect(); }} onDoubleClick={event => { event.stopPropagation(); if (!action.disabled) onPrimary(); }}>{source.displayTitle || source.title}</button></h3>;
}
export function SourceMeta({ source, topics, onTopic }: Pick<SourceViewProps, "source" | "topics" | "onTopic">) {
  return <div className="library-source-meta"><span>{[source.venue, source.publishedAt].filter(Boolean).join(" · ")}</span>{source.topicIds.map(id => <a href="/library" key={id} onClick={event => { event.preventDefault(); event.stopPropagation(); onTopic(id); }} onDoubleClick={event => event.stopPropagation()}>#{topics.find(t => t.topicId === id)?.title ?? id}</a>)}{source.topicIds.length === 0 && <span>未归类</span>}</div>;
}
export function SourceState({ source, status, candidate, bar = true }: Pick<SourceViewProps, "source" | "status" | "candidate"> & { bar?: boolean }) {
  return <div className="library-source-status" data-tone={status.tone}><span><i aria-hidden="true" />{status.label}<small>{status.detail}{candidate ? " · 新计划可用" : ""}</small></span>{bar && <LibraryProgress label={`${source.title} 阅读进度`} value={status.ratio * Math.max(1, source.progress.total)} max={source.progress.total || 1} />}</div>;
}
export function SourceArtifacts({ source, blog, onOverview, onBlog }: Pick<SourceViewProps, "source" | "blog" | "onOverview" | "onBlog">) {
  const summary = blogSummary(blog);
  return <div className="library-source-artifacts"><span title={`${source.noteCount} 条笔记`}>✎ {source.noteCount}</span><button type="button" disabled={!onOverview} onClick={event => { event.stopPropagation(); onOverview?.(); }} onDoubleClick={event => event.stopPropagation()}>文章结构</button><button type="button" onClick={event => { event.stopPropagation(); onBlog?.(); }} onDoubleClick={event => event.stopPropagation()} data-tone={summary.tone} title={summary.label} aria-label={`博客：${summary.label}`}><i aria-hidden="true" />带读博客</button></div>;
}
export function SourcePrimary({ action, onPrimary, solid = false }: Pick<SourceViewProps, "action" | "onPrimary"> & { solid?: boolean }) {
  return <button className={solid ? "workspace-primary" : "library-source-primary"} title={action.title} disabled={action.disabled} onClick={event => { event.stopPropagation(); onPrimary(); }} onDoubleClick={event => event.stopPropagation()}>{action.label}</button>;
}
