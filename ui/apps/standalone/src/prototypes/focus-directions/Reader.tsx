import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { figures, units, type FigureRef } from "./data";
import type { Demo } from "./engine";
import { Ctx, TimelineA, TimelineAB, TimelineB, TimelineC, chronological, groupByUnit, type ReaderCtx } from "./parts";
import { useReadingScroll } from "./scroll";
import { FigureViewer, type ViewerRequest } from "./viewer";

export type Direction = "a" | "ab" | "b" | "c";
export type Settings = { k: number; reduced: boolean; autoFigures: boolean; yieldText: boolean };
type DrawerTab = "figures" | "notes" | "progress" | "discussion";
type Quote = { unit: number; excerpt: string };

function findRange(root: Element, text: string): Range | null {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => (n.parentElement?.closest(".katex-mathml") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes: { node: Text; start: number }[] = [];
  let all = "";
  while (walker.nextNode()) { const node = walker.currentNode as Text; nodes.push({ node, start: all.length }); all += node.data; }
  let at = all.indexOf(text), len = text.length;
  if (at < 0) { const probe = text.slice(0, 10); at = all.indexOf(probe); len = probe.length; }
  if (at < 0) return null;
  const locate = (offset: number) => { const hit = [...nodes].reverse().find(n => n.start <= offset)!; return { node: hit.node, offset: offset - hit.start }; };
  const a = locate(at), b = locate(at + len);
  const range = document.createRange(); range.setStart(a.node, a.offset); range.setEnd(b.node, Math.min(b.offset, b.node.length));
  return range;
}
function setHighlight(name: string, range: Range | null) {
  if (!("highlights" in CSS) || typeof Highlight === "undefined") return;
  if (range) CSS.highlights.set(name, new Highlight(range)); else CSS.highlights.delete(name);
}

export function Reader({ direction, demo, settings, fullscreen, setFullscreen }: {
  direction: Direction; demo: Demo; settings: Settings; fullscreen: boolean; setFullscreen: (v: boolean) => void;
}) {
  const { k, reduced } = settings;
  const streaming = !!demo.streamingId;
  const s = useReadingScroll({ k, reduced, streaming });
  const stage = useRef<HTMLDivElement>(null);
  const column = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const drawerButton = useRef<HTMLButtonElement>(null);
  const [drawer, setDrawer] = useState<{ open: boolean; tab: DrawerTab; figure: string | null }>({ open: false, tab: "figures", figure: null });
  const [outline, setOutline] = useState(false);
  const [draft, setDraft] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [viewer, setViewer] = useState<ViewerRequest | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [selectionTip, setSelectionTip] = useState<{ x: number; y: number; unit: number; text: string } | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [shift, setShift] = useState(0);
  const [wide, setWide] = useState(false);
  const split = direction === "ab" && wide && !drawer.open;

  const focusUnit = s.viewing ?? demo.frontier;
  const reviewing = s.viewing !== null && s.viewing < demo.frontier;
  const groups = useMemo(() => (direction === "c" ? chronological : groupByUnit)(demo.timeline, demo.messages), [direction, demo.timeline, demo.messages]);
  const loadedFigures = useMemo(() => Object.values(figures).filter(f => f.unit <= demo.frontier), [demo.frontier]);

  // Only content created after mount may play an entrance; restored history never replays.
  const seen = useRef<Set<string> | null>(null);
  const mounted = useRef(false);
  const fresh = useCallback((key: string) => {
    if (!seen.current) seen.current = new Set();
    const isNew = mounted.current && !seen.current.has(key);
    seen.current.add(key);
    return isNew;
  }, []);

  const flash = useCallback((unit: number, text?: string) => {
    const root = s.pane.current?.querySelector(`[data-source-text="${unit}"]`);
    if (!root || !text) return;
    setHighlight("fd-flash", findRange(root, text));
    window.setTimeout(() => setHighlight("fd-flash", null), 2400 * k);
  }, [k, s.pane]);

  const unitEl = (unit: number) => s.pane.current?.querySelector(`[data-unit="${unit}"]`) ?? null;

  const ctx: ReaderCtx = {
    demo, focusUnit, reviewing, fresh, split,
    quote: (unit, excerpt) => {
      setQuote({ unit, excerpt: excerpt ?? units[unit - 1].title });
      setCollapsed(false); setSelectionTip(null);
      requestAnimationFrame(() => textarea.current?.focus({ preventScroll: true }));
    },
    openFigure: (figure, origin) => setViewer({ figure, origin }),
    pinFigure: figure => toggleDrawer(true, { tab: "figures", figure: figure.id }),
    jumpToSource: (unit, text) => {
      const el = s.pane.current?.querySelector(`[data-source-text="${unit}"]`);
      if (!el) { setToast(`第 ${unit} 段不在当前会话中（演示）`); return; }
      let target: Element = el;
      const range = text ? findRange(el, text) : null;
      if (range) { const marker = range.startContainer.parentElement; if (marker) target = marker; }
      s.jump(target, unit);
      flash(unit, text);
    },
    saveNote: (unit, text) => { demo.addNote(unit, text); setToast("已存为笔记 · 可在资料栏查看（演示）"); },
    linkQuote: (unit, text) => {
      const root = s.pane.current?.querySelector(`[data-source-text="${unit}"]`);
      setHighlight("fd-link", root && text ? findRange(root, text) : null);
    },
  };

  useLayoutEffect(() => {
    s.land(unitEl(demo.frontier), { instant: true, unit: demo.frontier });
    mounted.current = true;
  }, []);

  // Continue: land the new paragraph at the reading start line; long paragraphs start from their top.
  const lastFrontier = useRef(demo.frontier);
  useLayoutEffect(() => {
    if (demo.frontier === lastFrontier.current) return;
    lastFrontier.current = demo.frontier;
    s.land(unitEl(demo.frontier), { unit: demo.frontier });
    const figs = units[demo.frontier - 1].figures;
    if (settings.autoFigures) { if (figs.length) toggleDrawer(true, { tab: "figures", figure: figs[0] }); else toggleDrawer(false); }
  }, [demo.frontier]);

  const lastLength = useRef(demo.timeline.length);
  useLayoutEffect(() => {
    const added = demo.timeline.slice(lastLength.current);
    lastLength.current = demo.timeline.length;
    const q = added.find(e => e.kind === "msg" && demo.messages[e.id]?.role === "user");
    if (q && q.kind === "msg") s.reveal(s.pane.current?.querySelector(`[data-msg="${q.id}"]`) ?? null);
    if (demo.timeline.length === 0) s.pane.current?.scrollTo({ top: 0 });
  }, [demo.timeline]);

  useLayoutEffect(() => {
    const place = () => {
      const st = stage.current, col = column.current, pane = s.pane.current;
      if (!st || !col || !pane) return;
      if (!drawer.open || !settings.yieldText) { setShift(0); return; }
      const drawerRight = 12 + Math.min(400, st.clientWidth - 24);
      const left = pane.offsetLeft + col.offsetLeft, right = left + col.offsetWidth;
      const need = drawerRight + 24 - left, room = pane.clientWidth - 16 - right;
      setShift(need > 0 ? Math.max(0, Math.min(need, room)) : 0);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [drawer.open, settings.yieldText, direction, fullscreen, split]);

  useLayoutEffect(() => {
    const measure = () => { const w = s.pane.current?.clientWidth ?? 0; setWide(old => { const next = w >= 1240; if (next !== old) s.capture(); return next; }); };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [fullscreen]);
  const lastSplit = useRef(split);
  useLayoutEffect(() => {
    if (lastSplit.current === split) return;
    lastSplit.current = split;
    s.restore(); s.sizeSpacer();
  }, [split]);
  function toggleDrawer(open: boolean, patch?: Partial<{ tab: DrawerTab; figure: string | null }>) {
    if (direction === "ab" && wide && open !== drawer.open) s.capture();
    setDrawer(d => ({ ...d, ...patch, open }));
  }

  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(null), 2600); return () => clearTimeout(t); }, [toast]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || viewer) return;
      if (outline) setOutline(false);
      else if (drawer.open) { toggleDrawer(false); drawerButton.current?.focus({ preventScroll: true }); }
      else if (fullscreen) setFullscreen(false);
      else return;
      e.preventDefault();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  });

  function onMouseUp() {
    const sel = getSelection();
    if (!sel || sel.isCollapsed || !stage.current) { setSelectionTip(null); return; }
    const host = (sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode?.parentElement)?.closest<HTMLElement>("[data-source-text]");
    const text = sel.toString().trim();
    if (!host || text.length < 2) { setSelectionTip(null); return; }
    const r = sel.getRangeAt(0).getBoundingClientRect(), base = stage.current.getBoundingClientRect();
    setSelectionTip({ x: r.left + r.width / 2 - base.left, y: r.top - base.top, unit: Number(host.dataset.sourceText), text: text.slice(0, 140) });
  }

  function send() {
    const text = draft.trim(); if (!text || streaming) return;
    const unit = quote?.unit ?? focusUnit;
    const id = demo.send(text, unit, quote?.excerpt);
    if (id) { setDraft(""); setQuote(null); }
  }

  const continueLabel = demo.completed ? "已读完" : demo.pending ? "打开中…" : demo.frontier >= units.length ? "完成本篇" : `继续 · 第 ${demo.frontier + 1} 段`;
  const Timeline = { a: TimelineA, ab: TimelineAB, b: TimelineB, c: TimelineC }[direction];

  return <Ctx.Provider value={ctx}>
    <div className="fd-app" data-fullscreen={fullscreen || undefined}>
      <nav className="fd-rail" aria-label="工作台导航">
        <span className="fd-logo">F<i>.</i></span>
        <button title="知识库"><Icon d="M4 5h16M4 12h16M4 19h10" /></button>
        <button title="阅读" aria-current="page"><Icon d="M5 4h9l5 5v11H5zM14 4v5h5" /></button>
        <button title="设置"><Icon d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" /></button>
      </nav>
      <div className="fd-main">
        <header className="fd-header">
          <span className="fd-title">片上存储层次与算子融合：Transformer 推理的性能建模</span>
          <span className="fd-demo-tag">模拟数据</span>
          <span className="fd-grow" />
          <span className="fd-task" data-active={streaming || undefined}><i />{streaming ? "1 项进行中" : "任务"}</span>
        </header>

        <div className="fd-stage" ref={stage} style={{ "--shift": `${shift}px` } as CSSProperties}>
          <div className="fd-pane" ref={s.pane} tabIndex={0} aria-label="阅读与讨论"
            onScroll={() => { s.onScroll(); setSelectionTip(null); }}
            onWheel={e => s.userIntent(e.deltaY < 0)}
            onTouchStart={() => s.userIntent(true)}
            onKeyDown={e => { if (["PageUp", "ArrowUp", "Home"].includes(e.key)) s.userIntent(true); else if (["PageDown", "ArrowDown", "End", " "].includes(e.key)) s.userIntent(false); }}
            onMouseUp={onMouseUp}>
            <div className={`fd-column fd-col-${direction}`} data-split={split || undefined} ref={column}>
              <div ref={s.content}>
                {demo.timeline.length === 0 && <section className="fd-empty">
                  <p className="fd-empty-kicker">新会话</p>
                  <h2>讨论已清空，阅读进度保留在第 {demo.frontier} 段</h2>
                  <p>旧讨论仍可在资料栏「讨论」中找到。继续阅读将从第 {Math.min(demo.frontier + 1, units.length)} 段开始。</p>
                  <button className="fd-primary" onClick={demo.continueReading}>继续阅读</button>
                </section>}
                <Timeline groups={groups} />
                {demo.completed && <section className="fd-done">已完成本篇 · <button className="fd-link">重新阅读（演示不执行）</button></section>}
              </div>
              <div ref={s.end} className="fd-end" />
              <div ref={s.spacer} aria-hidden="true" />
            </div>
          </div>

          <div className="fd-pills" aria-live="polite">
            {s.returnTo !== null && <button className="fd-pill" onClick={s.goBack}>↩ 返回刚才位置</button>}
            {s.showLatest && <button className="fd-pill fd-pill-strong" onClick={s.toLatest}>{streaming ? "回答生成中 · 回到最新 ↓" : "回到最新 ↓"}</button>}
          </div>

          {selectionTip && <button className="fd-seltip" style={{ left: selectionTip.x, top: selectionTip.y }}
            onMouseDown={e => e.preventDefault()} onClick={() => { ctx.quote(selectionTip.unit, selectionTip.text); getSelection()?.removeAllRanges(); }}>
            引用所选提问
          </button>}

          <aside className="fd-drawer" data-open={drawer.open} aria-label="阅读资料" inert={!drawer.open}>
            <header className="fd-drawer-head">
              <div className="fd-seg" role="tablist">
                {(["figures", "notes", "progress", "discussion"] as const).map(t => <button key={t} role="tab" aria-selected={drawer.tab === t} onClick={() => setDrawer(d => ({ ...d, tab: t }))}>
                  {{ figures: `图片 ${loadedFigures.length}`, notes: `笔记 ${demo.notes.length}`, progress: "进度", discussion: "讨论" }[t]}
                </button>)}
              </div>
              <button className="fd-ghost fd-icon" aria-label="关闭资料" onClick={() => { toggleDrawer(false); drawerButton.current?.focus({ preventScroll: true }); }}>✕</button>
            </header>
            <div className="fd-drawer-body">
              {drawer.tab === "figures" && <FiguresTab list={loadedFigures} selected={drawer.figure ?? loadedFigures.at(-1)?.id ?? null}
                onSelect={id => setDrawer(d => ({ ...d, figure: id }))} onOpen={(f, el) => setViewer({ figure: f, origin: el })} onJump={u => ctx.jumpToSource(u)} />}
              {drawer.tab === "notes" && <div className="fd-notes">
                <textarea value={noteDraft} onChange={e => setNoteDraft(e.target.value)} placeholder={`为第 ${focusUnit} 段写笔记…`} rows={3} />
                <button className="fd-secondary" disabled={!noteDraft.trim()} onClick={() => { demo.addNote(focusUnit, noteDraft.trim()); setNoteDraft(""); setToast("笔记已保存（演示）"); }}>保存笔记</button>
                {demo.notes.map(n => <article key={n.id} className="fd-note"><button className="fd-link" onClick={() => ctx.jumpToSource(n.unit)}>第 {n.unit} 段</button><p>{n.text}</p></article>)}
              </div>}
              {drawer.tab === "progress" && <ol className="fd-list">{units.map(u => <li key={u.index}>
                <button disabled={u.index > demo.frontier} onClick={() => ctx.jumpToSource(u.index)} data-current={u.index === focusUnit || undefined}>
                  <span className="fd-idx">{String(u.index).padStart(2, "0")}</span>{u.section}<span className="fd-grow" />{u.index < demo.frontier ? "已读" : u.index === demo.frontier ? "当前" : "未读"}
                </button></li>)}</ol>}
              {drawer.tab === "discussion" && <ol className="fd-list">{Object.values(demo.messages).filter(m => m.role === "user").map(m => <li key={m.id}>
                <button onClick={() => { const el = s.pane.current?.querySelector(`[data-msg="${m.id}"]`); if (el) s.jump(el, m.unit); else setToast("这条讨论属于旧会话（演示）"); }}>
                  <span className="fd-idx">§{m.unit}</span><span className="fd-ellipsis">{m.text}</span></button></li>)}</ol>}
            </div>
          </aside>
        </div>

        <div className="fd-dock" style={{ "--shift": `${shift}px` } as CSSProperties} data-direction={direction}>
          <div className="fd-actions" role="toolbar" aria-label="阅读功能">
            <button ref={drawerButton} className="fd-ghost" aria-expanded={drawer.open} onClick={() => toggleDrawer(!drawer.open)}>
              <Icon d="M4 5h6v14H4zM13 5h7M13 10h7M13 15h5" /> 资料
            </button>
            <div className="fd-popover-anchor">
              <button className="fd-locator" data-review={reviewing || undefined} aria-expanded={outline} onClick={() => setOutline(v => !v)} title="文章结构与阅读位置">
                {reviewing ? <><b>回看 {s.viewing}</b><span>· 进度 {demo.frontier}/{units.length}</span></> : <><b>{focusUnit}/{units.length}</b><span>{units[focusUnit - 1]?.section}</span></>}
                <span className="fd-caret-down">▾</span>
              </button>
              {reviewing && <button className="fd-ghost fd-sm" onClick={() => s.land(unitEl(demo.frontier), { unit: demo.frontier })}>回到进度</button>}
              <div className="fd-popover" data-open={outline} inert={!outline}>
                <p className="fd-popover-title">文章结构 · 已读 {demo.frontier} / {units.length}</p>
                <ol>{units.map(u => <li key={u.index}><button disabled={u.index > demo.frontier} data-current={u.index === focusUnit || undefined}
                  onClick={() => { setOutline(false); s.jump(unitEl(u.index), u.index); }}>
                  <span className="fd-idx">{String(u.index).padStart(2, "0")}</span><span className="fd-ellipsis">{u.section} · {u.title}</span>
                  {u.index === demo.frontier && <span className="fd-frontier">进度</span>}
                </button></li>)}</ol>
              </div>
            </div>
            <span className="fd-grow" />
            <button className="fd-ghost" disabled={streaming || demo.pending} onClick={demo.newSession}>新会话</button>
            <button className="fd-ghost" aria-pressed={fullscreen} onClick={() => setFullscreen(!fullscreen)}>{fullscreen ? "退出全屏" : "全屏"}</button>
            {collapsed && <button className="fd-ghost" onClick={() => { setCollapsed(false); requestAnimationFrame(() => textarea.current?.focus({ preventScroll: true })); }}>
              提问{(draft || quote) && <i className="fd-dot" title="有未发送的草稿" />}
            </button>}
            {collapsed && streaming && <button className="fd-ghost fd-danger" onClick={demo.stop}>停止</button>}
            <button className="fd-primary" disabled={demo.completed || demo.pending || streaming} onClick={demo.continueReading}>{continueLabel}</button>
          </div>
          <div className="fd-composer-wrap" data-collapsed={collapsed} inert={collapsed}>
            <div className="fd-composer-clip">
              <form className="fd-composer" onSubmit={e => { e.preventDefault(); send(); }}>
                {quote && <div className="fd-quote-chip"><span className="fd-quote-mark">引用第 {quote.unit} 段</span><span className="fd-ellipsis">{quote.excerpt}</span>
                  <button type="button" className="fd-ghost fd-icon" aria-label="移除引用" onClick={() => setQuote(null)}>✕</button></div>}
                <textarea ref={textarea} rows={1} value={draft} placeholder={`就第 ${quote?.unit ?? focusUnit} 段提问…`}
                  onChange={e => { setDraft(e.target.value); e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`; }}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); send(); } }} />
                <div className="fd-chin">
                  <button type="button" className="fd-ghost fd-sm" onClick={() => { s.reserve((document.querySelector(".fd-composer-wrap") as HTMLElement | null)?.offsetHeight ?? 0); setCollapsed(true); }} title="收起输入区，草稿会保留">收起</button>
                  <span className="fd-hint">Enter 发送 · Shift+Enter 换行 · 选中原文可直接引用</span>
                  <span className="fd-grow" />
                  {streaming ? <button type="button" className="fd-send" data-stop onClick={demo.stop}>停止</button>
                    : <button type="submit" className="fd-send" disabled={!draft.trim()}>发送</button>}
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
      {viewer && <FigureViewer request={viewer} list={loadedFigures.length ? loadedFigures : [viewer.figure]} k={k} reduced={reduced} onClose={() => setViewer(null)} />}
      <div className="fd-toast" data-open={!!toast} role="status">{toast}</div>
    </div>
  </Ctx.Provider>;
}

function FiguresTab({ list, selected, onSelect, onOpen, onJump }: {
  list: FigureRef[]; selected: string | null; onSelect: (id: string) => void; onOpen: (f: FigureRef, el: HTMLElement) => void; onJump: (unit: number) => void;
}) {
  const current = list.find(f => f.id === selected) ?? list.at(-1);
  if (!current) return <p className="fd-muted">已读段落中还没有图片。</p>;
  return <div className="fd-figtab">
    <button className="fd-figbig" data-fig-origin={`drawer-${current.id}`} onClick={e => onOpen(current, e.currentTarget)} aria-label={`放大${current.label}`}><img src={current.src} alt={current.caption} /></button>
    <p className="fd-figcap">{current.caption} <button className="fd-link" onClick={() => onJump(current.unit)}>回到第 {current.unit} 段</button></p>
    <div className="fd-figgrid">{list.map(f => <button key={f.id} aria-pressed={f.id === current.id} onClick={() => onSelect(f.id)}><img src={f.src} alt="" /><span>{f.label} · §{f.unit}</span></button>)}</div>
  </div>;
}

function Icon({ d }: { d: string }) {
  return <svg className="fd-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
}