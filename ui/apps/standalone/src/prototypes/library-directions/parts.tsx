import { useEffect, useLayoutEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import type { BlogArtifactName, LibraryTopic } from "@focus/reader-contracts";
import type { DemoIngestion, DemoSource } from "./data";
import { blogSummary, phaseLabel, phaseOf, phaseTone, primaryAction, progressRatio, statusDetail, title } from "./model";
import type { Library } from "./store";

const reduced = () => document.documentElement.dataset.motion === "reduced";
const ms = (name: string) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name)) || 0;

/** FLIP for Topic reordering: rows keep identity, only their position travels. */
export function useFlip(order: string, root: React.RefObject<HTMLElement | null>) {
  const last = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const el = root.current; if (!el) return;
    const next = new Map<string, number>();
    el.querySelectorAll<HTMLElement>("[data-flip]").forEach(node => {
      const key = node.dataset.flip!, top = node.getBoundingClientRect().top;
      next.set(key, top);
      const before = last.current.get(key);
      if (before !== undefined && Math.abs(before - top) > 1 && !reduced()) {
        node.animate([{ transform: `translateY(${before - top}px)` }, { transform: "none" }],
          { duration: ms("--lb-travel"), easing: "cubic-bezier(.45,0,.2,1)" });
      }
    });
    last.current = next;
  }, [order, root]);
}

export function KindBadge({ s }: { s: DemoSource }) {
  return <span className="lb-kind" data-kind={s.kind} title={s.kind === "paper" ? "Paper Source" : "Article Source"}>{s.format ?? (s.kind === "paper" ? "PDF" : "HTML")}</span>;
}

export function Status({ s, bar = true }: { s: DemoSource; bar?: boolean }) {
  const phase = phaseOf(s), detail = statusDetail(s);
  return <div className="lb-status" data-tone={phaseTone[phase]}>
    <span className="lb-status__label"><i aria-hidden="true" />{phaseLabel[phase]}{detail && <small>{detail}</small>}</span>
    {bar && (phase === "reading" || phase === "preparing" || phase === "prepFailed" || phase === "completed") &&
      <span className="lb-bar" aria-hidden="true"><span style={{ transform: `scaleX(${phase === "completed" ? 1 : progressRatio(s)})` }} /></span>}
  </div>;
}

export function Artifacts({ s }: { s: DemoSource }) {
  const blog = blogSummary(s);
  return <span className="lb-artifacts">
    <span title={`${s.noteCount} 条笔记`} data-empty={s.noteCount === 0}>✎ {s.noteCount}</span>
    <span className="lb-blog-dot" data-tone={blog.tone} title={blog.label}><i aria-hidden="true" />博客</span>
  </span>;
}

export function Meta({ s, topics, onTopic }: { s: DemoSource; topics: readonly LibraryTopic[]; onTopic?: (id: string) => void }) {
  const parts = [s.venue, s.publishedAt].filter(Boolean);
  return <div className="lb-meta">
    {parts.length > 0 && <span>{parts.join(" · ")}</span>}
    {s.topicIds.map(id => <button key={id} type="button" className="lb-tag" onClick={e => { e.stopPropagation(); onTopic?.(id); }}>
      #{topics.find(t => t.topicId === id)?.title ?? id}</button>)}
    {s.topicIds.length === 0 && <span className="lb-faint">未归类</span>}
  </div>;
}

export function MoreMenu({ s, lib }: { s: DemoSource; lib: Library }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const act = (text: string) => { setOpen(false); lib.say(text); };
  return <div className="lb-more" ref={box} onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } }}>
    <button type="button" className="lb-icon-btn" aria-label={`${title(s)} 更多操作`} aria-expanded={open} onClick={() => setOpen(!open)}>⋯</button>
    <div className="lb-menu" data-open={open} role="menu">
      <button role="menuitem" onClick={() => act("原型：打开现有「管理来源」对话框")}>编辑标题与专题</button>
      <button role="menuitem" disabled={s.parseStatus !== "ready"} onClick={() => act("原型：确认后重新规划，保留旧计划、译文和笔记")}>重新规划</button>
      <button role="menuitem" onClick={() => act("原型：确认后清除讨论、笔记和阅读记录，从第一段重新开始")}>重新阅读</button>
      <hr />
      <button role="menuitem" className="lb-danger" onClick={() => act("原型：先读取删除影响，再确认永久删除")}>删除…</button>
    </div>
  </div>;
}

type RowProps = {
  s: DemoSource; lib: Library; topics: readonly LibraryTopic[]; selected: boolean; fresh?: boolean; ordinal?: number;
  onSelect: () => void; onPrimary: () => void; onTopic: (id: string) => void;
  drag?: { onStart: () => void; onOver: () => void; onEnd: () => void; onKeyMove: (offset: number) => void; dragging: boolean };
};
export function SourceRow({ s, lib, topics, selected, fresh, ordinal, onSelect, onPrimary, onTopic, drag }: RowProps) {
  const action = primaryAction(s);
  return <div className="lb-row" data-flip={s.sourceId} data-selected={selected} data-fresh={fresh} data-dragging={drag?.dragging}
    data-phase={phaseOf(s)} draggable={!!drag}
    onDragStart={(e: DragEvent) => { if (!drag) return; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", s.sourceId); drag.onStart(); }}
    onDragOver={(e: DragEvent) => { if (!drag) return; e.preventDefault(); drag.onOver(); }}
    onDragEnd={() => drag?.onEnd()} onDrop={e => { e.preventDefault(); drag?.onEnd(); }}
    onClick={onSelect} onDoubleClick={() => !action.disabled && onPrimary()}>
    {ordinal !== undefined && <span className="lb-ordinal" aria-hidden="true"><span className="lb-grip">⋮⋮</span><span>{ordinal}</span></span>}
    <KindBadge s={s} />
    <div className="lb-row__main">
      <button type="button" className="lb-row__title" aria-pressed={selected} title={s.title}
        onKeyDown={e => { if (drag && e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) { e.preventDefault(); drag.onKeyMove(e.key === "ArrowUp" ? -1 : 1); } }}>
        {title(s)}</button>
      <Meta s={s} topics={topics} onTopic={onTopic} />
    </div>
    <Status s={s} />
    <Artifacts s={s} />
    <button type="button" className="lb-row-action" disabled={action.disabled} data-phase={phaseOf(s)}
      onClick={e => { e.stopPropagation(); onPrimary(); }}>{action.label}</button>
    <MoreMenu s={s} lib={lib} />
  </div>;
}

export function SourceCard({ s, lib, topics, selected, fresh, onSelect, onPrimary, onTopic }: RowProps) {
  const action = primaryAction(s);
  return <article className="lb-card" data-selected={selected} data-fresh={fresh} data-phase={phaseOf(s)} onClick={onSelect}>
    <div className="lb-card__top"><KindBadge s={s} /><Status s={s} bar={false} /><span className="lb-grow" /><MoreMenu s={s} lib={lib} /></div>
    <button type="button" className="lb-card__title" aria-pressed={selected} title={s.title}>{title(s)}</button>
    <Meta s={s} topics={topics} onTopic={onTopic} />
    <div className="lb-card__foot">
      <span className="lb-bar" aria-hidden="true"><span style={{ transform: `scaleX(${phaseOf(s) === "completed" ? 1 : progressRatio(s)})` }} /></span>
      <Artifacts s={s} />
      <button type="button" className="lb-row-action" disabled={action.disabled}
        onClick={e => { e.stopPropagation(); onPrimary(); }}>{action.label}</button>
    </div>
  </article>;
}

const backendLabel = { "local-mineru": "本地 MinerU", "remote-mineru": "远端 MinerU API", html: "本地 HTML 解析" };
export function ShadowRow({ i, topics, onRetry, onTasks }: { i: DemoIngestion; topics: readonly LibraryTopic[]; onRetry: () => void; onTasks: () => void }) {
  return <div className="lb-shadow" data-failed={!!i.failed} role="status">
    <span className="lb-kind" data-kind="pending">{/\.pdf$/i.test(i.fileName) ? "PDF" : "HTML"}</span>
    <div className="lb-row__main">
      <strong>{i.fileName}</strong>
      <div className="lb-meta"><span>{i.failed ? i.failed : `${backendLabel[i.backend]} · 解析中 ${i.percent}%`}</span>
        <span className="lb-faint">{i.topicId ? `将加入 #${topics.find(t => t.topicId === i.topicId)?.title}` : "不关联专题"}</span></div>
    </div>
    {!i.failed && <span className="lb-bar lb-bar--wide" aria-hidden="true"><span style={{ transform: `scaleX(${i.percent / 100})` }} /></span>}
    {i.failed ? <button type="button" className="lb-row-action" onClick={onRetry}>继续处理</button> : <span className="lb-faint">入库中</span>}
    <button type="button" className="lb-text-btn" onClick={onTasks}>任务详情</button>
  </div>;
}

const artifactNames: [BlogArtifactName, string][] = [["value_analysis", "价值分析"], ["reading_blog", "带读博客"], ["html", "HTML"]];
const artifactText = { pending: "待生成", generating: "生成中", completed: "已完成", failed: "失败", not_applicable: "不适用" };

export function Inspector({ s, topics, lib, open, onClose, onPrimary, docked }: {
  s: DemoSource | null; topics: readonly LibraryTopic[]; lib: Library; open: boolean; onClose: () => void; onPrimary: (s: DemoSource) => void; docked: boolean;
}) {
  const [shown, setShown] = useState(s);
  useEffect(() => { if (s) setShown(s); }, [s]);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => { if (open) panel.current?.focus({ preventScroll: true }); }, [open, s?.sourceId]);
  const v = s ?? shown;
  return <aside ref={panel} className="lb-inspector" data-open={open} data-docked={docked} tabIndex={-1} aria-label="来源详情" aria-hidden={!open}
    onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}>
    {v && <InspectorBody s={v} topics={topics} lib={lib} onClose={onClose} onPrimary={() => onPrimary(v)} />}
  </aside>;
}

function Section({ title: t, children, tone }: { title: string; children: ReactNode; tone?: "danger" }) {
  return <section className="lb-insp-section" data-tone={tone}><h3>{t}</h3>{children}</section>;
}

function InspectorBody({ s, topics, lib, onClose, onPrimary }: { s: DemoSource; topics: readonly LibraryTopic[]; lib: Library; onClose: () => void; onPrimary: () => void }) {
  const action = primaryAction(s), phase = phaseOf(s), blog = blogSummary(s);
  return <>
    <header className="lb-insp-head">
      <KindBadge s={s} /><span className="lb-grow" />
      <button type="button" className="lb-icon-btn" aria-label="关闭详情" onClick={onClose}>×</button>
    </header>
    <div className="lb-insp-scroll">
      <h2 className="lb-insp-title">{title(s)}</h2>
      {s.displayTitle && <p className="lb-insp-original">{s.title}</p>}
      <div className="lb-insp-cta">
        <Status s={s} />
        <button type="button" className="lb-primary" disabled={action.disabled} onClick={onPrimary}>{action.label}</button>
      </div>
      {phase === "invalid" && <p className="lb-callout" data-tone="danger">{s.error}</p>}
      {phase === "prepFailed" && <p className="lb-callout" data-tone="warning">准备在第 {s.preparing!.completed}/{s.preparing!.total} 段中断：{s.preparing!.failed}</p>}
      {phase === "preparing" && <p className="lb-callout">正在翻译 · {s.preparing!.completed}/{s.preparing!.total} 段。完成后可手动开始阅读。</p>}

      <Section title="专题">
        <div className="lb-chips">
          {s.topicIds.map(id => <span key={id} className="lb-chip">#{topics.find(t => t.topicId === id)?.title ?? id}</span>)}
          {s.topicIds.length === 0 && <span className="lb-faint">未归类</span>}
          <button type="button" className="lb-text-btn" onClick={() => lib.say("原型：打开现有「管理来源」对话框（标题与所属专题一起保存）")}>编辑</button>
        </div>
        <p className="lb-hint">同一来源在多个专题中指向同一份资产；移出专题不删除来源。</p>
      </Section>

      <Section title="博客">
        <ul className="lb-artifact-list">
          {artifactNames.map(([name, label]) => <li key={name} data-status={s.blog.artifacts[name]}><span>{label}</span><small>{artifactText[s.blog.artifacts[name]]}</small></li>)}
        </ul>
        {s.blog.valueAnalysisReason && <p className="lb-hint">价值分析不适用：{s.blog.valueAnalysisReason}</p>}
        <div className="lb-btn-row">
          {blog.tone === "done" && <button type="button" onClick={() => lib.say("原型：在查看器中打开合并 HTML 博客")}>打开博客</button>}
          {blog.tone === "none" && <button type="button" disabled={s.parseStatus !== "ready"} onClick={() => lib.say("原型：开始生成 Blog Output")}>生成博客</button>}
          {blog.tone === "running" && <button type="button" onClick={() => lib.say("原型：取消博客生成")}>取消生成</button>}
          {artifactNames.filter(([n]) => s.blog.artifacts[n] === "failed").map(([n, label]) =>
            <button key={n} type="button" onClick={() => lib.say(`原型：只重新生成${label}`)}>重新生成{label}</button>)}
        </div>
      </Section>

      <Section title="来源">
        <dl className="lb-facts">
          {s.venue && <><dt>出处</dt><dd>{s.venue}</dd></>}
          {s.publishedAt && <><dt>日期</dt><dd>{s.publishedAt}</dd></>}
          <dt>笔记</dt><dd>{s.noteCount} 条</dd>
          <dt>解析</dt><dd>{s.parseStatus === "ready" ? "Parser Bundle 已校验" : "校验失败"}</dd>
          <dt>Source ID</dt><dd><code>{s.sourceId}</code></dd>
        </dl>
        <div className="lb-btn-row">
          <button type="button" className="lb-text-btn" onClick={() => lib.say("原型：新窗口打开原件")}>原件 ↗</button>
          <button type="button" className="lb-text-btn" disabled={s.parseStatus !== "ready"} onClick={() => lib.say("原型：新窗口打开解析正文")}>正文 ↗</button>
          <button type="button" className="lb-text-btn" onClick={() => lib.say("原型：打开现有「管理来源」对话框")}>编辑标题</button>
        </div>
      </Section>

      <Section title="重置与删除" tone="danger">
        <div className="lb-btn-row">
          <button type="button" disabled={s.parseStatus !== "ready"} onClick={() => lib.say("原型：确认后重新规划，保留旧计划、译文和笔记")}>重新规划</button>
          <button type="button" onClick={() => lib.say("原型：确认后清除讨论、笔记和阅读记录")}>重新阅读</button>
          <button type="button" className="lb-danger" onClick={() => lib.say("原型：先读取删除影响，再确认永久删除")}>删除来源…</button>
        </div>
      </Section>
    </div>
  </>;
}

export type EmptyKind = "library" | "search" | "filter" | "offline" | "topic";
const emptyCopy: Record<EmptyKind, [string, string, string]> = {
  library: ["▤", "知识库还是空的。把 PDF 或 SingleFile HTML 拖到这里，或点击上传。", "上传材料"],
  search: ["⌕", "没有标题匹配这次搜索。", "清除搜索"],
  filter: ["◌", "当前筛选下没有材料。", "显示全部状态"],
  topic: ["#", "这个专题还没有来源。可从任意来源的详情中加入专题。", "查看全部材料"],
  offline: ["!", "无法连接 FOCUS 后端，列表未能读取。已有数据未受影响。", "重新连接"],
};
export function EmptyState({ kind, onAction }: { kind: EmptyKind; onAction: () => void }) {
  const [icon, text, action] = emptyCopy[kind];
  return <div className="lb-empty" data-kind={kind} role={kind === "offline" ? "alert" : "status"}>
    <span aria-hidden="true">{icon}</span><p>{text}</p>
    <button type="button" className={kind === "library" ? "lb-primary" : undefined} onClick={onAction}>{action}</button>
  </div>;
}
