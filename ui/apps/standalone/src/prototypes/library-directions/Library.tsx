import { useEffect, useMemo, useRef, useState } from "react";
import type { LibraryTopic } from "@focus/reader-contracts";
import { currentReading, type DemoSource } from "./data";
import { matchesQuery, matchesStatus, phaseOf, phaseLabel, phaseTone, primaryAction, statusFilters, title, UNFILED, type StatusFilter } from "./model";
import { EmptyState, Inspector, ShadowRow, SourceCard, SourceRow, useFlip, type EmptyKind } from "./parts";
import type { Library as Lib } from "./store";

/* Selected direction A: list + details panel (2026-10-20). */
export function Library({ lib }: { lib: Lib }) {
  const { sources, topics, ingestions } = lib;
  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [view, setView] = useState<"list" | "cards">("list");
  const [selected, setSelected] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [tasks, setTasks] = useState(false);
  const layout = useRef<HTMLDivElement>(null);
  const [docked, setDocked] = useState(true);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = layout.current; if (!el) return;
    const ro = new ResizeObserver(([entry]) => setDocked(entry.contentRect.width >= 1040));
    ro.observe(el); return () => ro.disconnect();
  }, []);

  const topicObj = topics.find(t => t.topicId === topic);
  const inScope = (s: DemoSource) => !topic || (topic === UNFILED ? s.topicIds.length === 0 : s.topicIds.includes(topic));
  const scoped = sources.filter(s => inScope(s) && matchesQuery(s, query));
  const visible = scoped.filter(s => matchesStatus(s, status));
  if (topicObj) visible.sort((a, b) => topicObj.sourceIds.indexOf(a.sourceId) - topicObj.sourceIds.indexOf(b.sourceId));
  const selectedSource = sources.find(s => s.sourceId === selected) ?? null;
  const current = sources.find(s => s.sourceId === currentReading.sourceId && phaseOf(s) === "reading");

  function select(id: string) { setSelected(id); setOpen(true); }
  function close() {
    setOpen(false);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-flip="${selected}"] .lb-row__title, [data-card="${selected}"] .lb-card__title`)?.focus());
  }
  function primary(s: DemoSource) {
    const a = primaryAction(s);
    if (phaseOf(s) === "invalid") { select(s.sourceId); return; }
    lib.say(`原型：${a.label} · ${title(s)}${["开始阅读", "继续阅读", "查看已读"].includes(a.label) ? " → 进入阅读页" : ""}`);
  }
  function upload(names: string[]) {
    if (!names.length) return;
    const target = topicObj?.topicId ?? null;
    lib.upload(names, target);
    lib.say(`原型：正式界面先打开现有上传对话框（专题默认为当前专题）；此处直接加入队列${target ? `，完成后加入 #${topicObj!.title}` : ""}`);
  }

  // ↑/↓ moves the selection through visible rows; Esc closes details and returns focus to the row.
  const order = useMemo(() => visible.map(s => s.sourceId), [visible]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || e.altKey || e.metaKey || e.ctrlKey || t.closest(".lb-menu, .lb-inspector, .fd-console")) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!order.length) return;
        e.preventDefault();
        const i = selected ? order.indexOf(selected) : -1;
        const next = order[Math.max(0, Math.min(order.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
        setSelected(next);
        if (open) setOpen(true);
        document.querySelector<HTMLElement>(`[data-flip="${next}"] .lb-row__title, [data-card="${next}"] .lb-card__title`)?.focus();
      } else if (e.key === "Escape" && open) close();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  });

  const emptyKind: EmptyKind | null = lib.offline ? "offline" : sources.length === 0 ? "library"
    : visible.length > 0 ? null : query ? "search" : status !== "all" ? "filter" : "topic";
  const resetEmpty = () => {
    if (emptyKind === "library") file.current?.click();
    else if (emptyKind === "search") setQuery("");
    else if (emptyKind === "filter") setStatus("all");
    else if (emptyKind === "topic") setTopic("");
    else lib.say("原型：重新请求 /library/sources");
  };
  const rowProps = (s: DemoSource) => ({ s, lib, topics, selected: selected === s.sourceId && open, fresh: lib.fresh.has(s.sourceId),
    onSelect: () => select(s.sourceId), onPrimary: () => primary(s), onTopic: setTopic });

  const heading = topicObj?.title ?? (topic === UNFILED ? "未归类" : "知识库");
  const scopeIngestions = ingestions.filter(i => !topic || i.topicId === topic);
  const ordered = !!topicObj && status === "all" && !query && view === "list";

  return <div className="lb-app"
    onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true); } }}
    onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
    onDrop={e => { if (!e.dataTransfer.files.length) return; e.preventDefault(); setDragging(false); upload(Array.from(e.dataTransfer.files).map(f => f.name)); }}>
    <Nav topics={topics} sources={sources} topic={topic} onTopic={setTopic} onCreate={() => lib.say("原型：打开现有「新建专题」对话框")} />
    <header className="lb-header">
      <h1>{heading}{!lib.offline && <small>{scoped.length} 份</small>}</h1>
      <select className="lb-topic-select" aria-label="专题" value={topic} onChange={e => setTopic(e.target.value)}>
        <option value="">全部材料</option>{topics.map(t => <option key={t.topicId} value={t.topicId}>{t.title}</option>)}<option value={UNFILED}>未归类</option></select>
      <span className="lb-grow" />
      <input type="search" className="lb-search" aria-label="搜索材料" placeholder="搜索标题、简称、出处" value={query} onChange={e => setQuery(e.target.value)} />
      <div className="lb-seg" role="group" aria-label="显示方式">{([["list", "列表"], ["cards", "卡片"]] as const).map(([v, label]) =>
        <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>{label}</button>)}</div>
      <div className="lb-tasks">
        <button type="button" className="lb-ghost" aria-expanded={tasks} onClick={() => setTasks(!tasks)}>
          <i className="lb-dot" data-active={ingestions.some(i => !i.failed)} data-attention={ingestions.some(i => i.failed)} aria-hidden="true" />
          {ingestions.length ? `${ingestions.length} 项` : "任务"}</button>
        <div className="lb-tasks__pop" data-open={tasks}>
          {ingestions.length === 0 ? <p>没有进行中或待处理的任务。</p> : ingestions.map(i => <p key={i.itemId}><strong>{i.fileName}</strong><br />{i.failed ?? `解析中 ${i.percent}%`}</p>)}
          <small>原型：正式界面沿用现有任务框的全部内容与操作。</small>
        </div>
      </div>
      <button type="button" className="lb-primary" onClick={() => file.current?.click()}>上传</button>
      <input ref={file} type="file" multiple hidden accept=".pdf,.html" onChange={e => { upload(Array.from(e.target.files ?? []).map(f => f.name)); e.target.value = ""; }} />
    </header>

    <div className="lb-layout" ref={layout} data-inspector={open && !!selectedSource} data-docked={docked}>
      <main className="lb-main">
        {emptyKind === "offline" || emptyKind === "library" ? <EmptyState kind={emptyKind} onAction={resetEmpty} /> : <>
          {!topic && current && !query && status === "all" && <ContinueStrip s={current} onPrimary={() => primary(current)} onSelect={() => select(current.sourceId)} />}
          {topicObj && <TopicHead t={topicObj} sources={sources} lib={lib} />}
          <Filters scoped={scoped} status={status} setStatus={setStatus} />
          {scopeIngestions.length > 0 && <div className="lb-rows lb-rows--pending" aria-label="入库中">{scopeIngestions.map(i =>
            <ShadowRow key={i.itemId} i={i} topics={topics} onRetry={() => lib.retryIngestion(i.itemId)} onTasks={() => setTasks(true)} />)}</div>}
          {emptyKind ? <EmptyState kind={emptyKind} onAction={resetEmpty} />
            : ordered ? <OrderedRows t={topicObj!} rows={visible} rowProps={rowProps} lib={lib} />
            : view === "list" ? <div className="lb-rows">{visible.map(s => <SourceRow key={s.sourceId} {...rowProps(s)} />)}</div>
            : <div className="lb-cards">{visible.map(s => <div key={s.sourceId} data-card={s.sourceId}><SourceCard {...rowProps(s)} /></div>)}</div>}
          {topicObj && !ordered && !emptyKind && <p className="lb-hint lb-center">{view === "cards" ? "切换到列表视图后可调整专题顺序。" : "筛选或搜索时暂停排序；清除条件后可拖动调整专题顺序。"}</p>}
        </>}
      </main>
      <Inspector s={open ? selectedSource : null} topics={topics} lib={lib} open={open && !!selectedSource} docked={docked} onClose={close} onPrimary={primary} />
    </div>

    <div className="lb-drop" data-open={dragging} aria-hidden={!dragging}>
      <div><strong>松开即可上传</strong><span>PDF 由服务器选择 MinerU 解析；SingleFile HTML 本地解析{topicObj ? ` · 默认加入 #${topicObj.title}` : ""}</span></div>
    </div>
    {lib.toast && <div key={lib.toast.id} className="lb-toast" role="status">{lib.toast.text}</div>}
  </div>;
}

function Nav({ topics, sources, topic, onTopic, onCreate }: { topics: readonly LibraryTopic[]; sources: readonly DemoSource[]; topic: string; onTopic: (id: string) => void; onCreate: () => void }) {
  const done = (ids: readonly string[]) => ids.filter(id => { const s = sources.find(x => x.sourceId === id); return s && phaseOf(s) === "completed"; }).length;
  const unfiled = sources.filter(s => s.topicIds.length === 0).length;
  return <aside className="lb-nav" aria-label="工作台导航">
    <div className="lb-logo">focus<span>.</span></div>
    <nav>{[["▤", "知识库", true], ["☷", "阅读", false], ["☼", "设置", false]].map(([icon, label, current]) =>
      <a key={label as string} href="#" aria-current={current ? "page" : undefined} onClick={e => e.preventDefault()}><span aria-hidden="true">{icon}</span>{label}</a>)}</nav>
    <div className="lb-nav-topics" role="group" aria-label="专题">
      <h2>专题</h2>
      <button type="button" aria-pressed={!topic} onClick={() => onTopic("")}>全部<span>{sources.length}</span></button>
      {topics.map(t => <button key={t.topicId} type="button" aria-pressed={topic === t.topicId} onClick={() => onTopic(t.topicId)}
        title={`已读完 ${done(t.sourceIds)} / ${t.sourceIds.length} 篇`}>
        {t.title}<span>{done(t.sourceIds)}/{t.sourceIds.length}</span></button>)}
      {unfiled > 0 && <button type="button" aria-pressed={topic === UNFILED} onClick={() => onTopic(UNFILED)}>未归类<span>{unfiled}</span></button>}
      <button type="button" className="lb-nav-new" onClick={onCreate}>＋ 新建专题</button>
    </div>
  </aside>;
}

function Filters({ scoped, status, setStatus }: { scoped: readonly DemoSource[]; status: StatusFilter; setStatus: (f: StatusFilter) => void }) {
  return <div className="lb-filters" role="group" aria-label="按状态筛选">
    {statusFilters.map(([f, label]) => { const n = scoped.filter(s => matchesStatus(s, f)).length;
      return <button key={f} type="button" aria-pressed={status === f} data-filter={f} disabled={n === 0 && f !== "all" && status !== f} onClick={() => setStatus(f)}>{label}<span>{n}</span></button>; })}
  </div>;
}

function ContinueStrip({ s, onPrimary, onSelect }: { s: DemoSource; onPrimary: () => void; onSelect: () => void }) {
  const { index, total, sectionPath } = currentReading;
  return <section className="lb-continue" aria-label="继续阅读">
    <div className="lb-continue__text" onClick={onSelect}>
      <small>上次阅读</small>
      <strong>{title(s)}</strong>
      <span>{sectionPath.at(-1)} · 第 {index} 段 / 共 {total} 段</span>
    </div>
    <span className="lb-bar lb-bar--wide" aria-hidden="true"><span style={{ transform: `scaleX(${(index - 1) / total})` }} /></span>
    <button type="button" className="lb-primary" onClick={onPrimary}>继续阅读</button>
  </section>;
}

function TopicHead({ t, sources, lib }: { t: LibraryTopic; sources: readonly DemoSource[]; lib: Lib }) {
  const members = t.sourceIds.map(id => sources.find(s => s.sourceId === id)).filter((s): s is DemoSource => !!s);
  const done = members.filter(s => phaseOf(s) === "completed").length, reading = members.filter(s => phaseOf(s) === "reading").length;
  return <section className="lb-topic-head" aria-label="专题概览">
    <div className="lb-topic-head__row">
      <p>已读完 <strong>{done}</strong> / {members.length} 篇{reading ? ` · ${reading} 篇阅读中` : ""}</p>
      <span className="lb-grow" />
      <button type="button" className="lb-text-btn" onClick={() => lib.say("原型：打开现有「重命名专题」对话框")}>重命名</button>
      <button type="button" className="lb-text-btn lb-danger" onClick={() => lib.say("原型：删除专题；来源、博客、笔记和阅读进度全部保留")}>删除专题</button>
    </div>
    <ol className="lb-segments" aria-label="专题顺序与状态">
      {members.map(s => <li key={s.sourceId} data-tone={phaseTone[phaseOf(s)]} title={`${title(s)} · ${phaseLabel[phaseOf(s)]}`} />)}
    </ol>
    <p className="lb-hint">顺序就是专题阅读顺序。拖动左侧序号，或在标题上按 Alt+↑/↓ 调整。</p>
  </section>;
}

type RowFactory = (s: DemoSource) => Parameters<typeof SourceRow>[0];

function OrderedRows({ t, rows, rowProps, lib }: { t: LibraryTopic; rows: readonly DemoSource[]; rowProps: RowFactory; lib: Lib }) {
  const [drag, setDrag] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useFlip(rows.map(r => r.sourceId).join("|"), box);
  const move = (id: string, targetId: string) => {
    if (id === targetId) return;
    const ids = t.sourceIds.filter(x => x !== id), at = ids.indexOf(targetId), from = t.sourceIds.indexOf(id), to = t.sourceIds.indexOf(targetId);
    ids.splice(from < to ? at + 1 : at, 0, id);
    lib.reorder(t.topicId, ids);
  };
  return <div className="lb-rows" ref={box} data-ordered="true">
    {rows.map(s => <SourceRow key={s.sourceId} {...rowProps(s)} ordinal={t.sourceIds.indexOf(s.sourceId) + 1}
      drag={{ dragging: drag === s.sourceId, onStart: () => setDrag(s.sourceId), onOver: () => drag && move(drag, s.sourceId), onEnd: () => setDrag(null),
        onKeyMove: offset => { const i = t.sourceIds.indexOf(s.sourceId), target = t.sourceIds[i + offset]; if (target) { move(s.sourceId, target);
          requestAnimationFrame(() => box.current?.querySelector<HTMLElement>(`[data-flip="${s.sourceId}"] .lb-row__title`)?.focus()); } } }} />)}
  </div>;
}
