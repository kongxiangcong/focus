// Throwaway prototype of the agreed reading direction, with state scenarios instead of visual variants.
import { createRoot } from "react-dom/client";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Icon } from "../lightfield/icons";
import { evidence, guide, scriptedAnswer, sections, type Answer, type Evidence } from "./data";
import "../../../../../packages/reader-ui/src/focus-tokens.css";
import "../../reading-fonts.css";
import "./prototype.css";

type Card = { evidence: Evidence; answerId: string; number: number; x: number; y: number; automatic: boolean };
const initialScenario = new URLSearchParams(location.search).get("scene") ?? "opening";
const scenarioLabels: Record<string, string> = { opening: "首次打开", normal: "多处证据", figure: "图表证据", block: "段落定位", web: "外部补充", missing: "定位失败", historical: "版本更新" };

function Prototype() {
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [renderedCard, setRenderedCard] = useState<Card | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [quote, setQuote] = useState("");
  const [selection, setSelection] = useState("");
  const [intro, setIntro] = useState(false);
  const [introOpen, setIntroOpen] = useState(true);
  const [introFailed, setIntroFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scene, setScene] = useState(initialScenario);
  const [dark, setDark] = useState(false);
  const [reduce, setReduce] = useState(false);
  const [osReduce, setOsReduce] = useState(matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [narrow, setNarrow] = useState(innerWidth < 960);
  const [mobile, setMobile] = useState<"source" | "chat">("chat");
  const [chatHidden, setChatHidden] = useState(false);
  const [ratio, setRatio] = useState(60);
  const [panel, setPanel] = useState<"contents" | "notes" | "more" | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [highlight, setHighlight] = useState(true);
  const [finished, setFinished] = useState(false);
  const [follow, setFollow] = useState(true);
  const [manual, setManual] = useState(false);
  const [hasReturn, setHasReturn] = useState(false);
  const [notice, setNotice] = useState("");
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const source = useRef<HTMLDivElement>(null);
  const sourcePane = useRef<HTMLElement>(null);
  const chat = useRef<HTMLDivElement>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const panelTrigger = useRef<HTMLElement | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const run = useRef(0);
  const nextId = useRef(1);
  const autoUsed = useRef(false);
  const manuallyBrowsing = useRef(false);
  const historyLocked = useRef(false);
  const following = useRef(true);
  const returnTop = useRef(0);
  const animation = useRef(0);
  const opener = useRef(0);
  const lowMotion = reduce || osReduce;
  const active = answers.find(a => a.id === activeId);
  const visibleEvidence = active?.parts.slice(0, active.shown).filter(p => p.evidence).map(p => p.evidence!) ?? [];
  const validEvidence = visibleEvidence.filter(e => !["unavailable", "historical"].includes(e.status ?? ""));

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);
  useEffect(() => {
    let frame = 0;
    if (card) { setRenderedCard(card); frame = requestAnimationFrame(() => setCardOpen(true)); }
    else setCardOpen(false);
    return () => cancelAnimationFrame(frame);
  }, [card]);
  useEffect(() => {
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => { setNarrow(innerWidth < 960); setCard(null); cancelAnimationFrame(animation.current); };
    const motion = () => setOsReduce(mq.matches);
    window.addEventListener("resize", update); mq.addEventListener("change", motion);
    return () => { window.removeEventListener("resize", update); mq.removeEventListener("change", motion); };
  }, []);
  useEffect(() => {
    const openingRun = run.current;
    const t = window.setTimeout(() => { setIntro(true); if (run.current === openingRun && initialScenario !== "opening") startScenario(initialScenario); }, 650);
    return () => { clearTimeout(t); run.current++; cancelAnimationFrame(animation.current); };
  }, []);
  useEffect(() => {
    if (answers.length && following.current && chat.current) chat.current.scrollTop = chat.current.scrollHeight;
  }, [answers, intro]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (panel) { setPanel(null); panelTrigger.current?.focus(); }
      else if (card) closeCard();
      else { setTooltip(null); setSelection(""); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, card]);

  function cancelNavigation() {
    cancelAnimationFrame(animation.current);
    opener.current++;
  }
  function sourceIntent() {
    cancelNavigation(); manuallyBrowsing.current = true; setManual(true); setCard(null); setTooltip(null);
  }
  function scrollTo(container: HTMLElement, top: number, instant: boolean, done?: () => void) {
    cancelAnimationFrame(animation.current);
    const from = container.scrollTop;
    const target = Math.max(0, Math.min(top, container.scrollHeight - container.clientHeight));
    if (instant || lowMotion || Math.abs(target - from) < 3) { container.scrollTop = target; done?.(); return; }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 240);
      container.scrollTop = from + (target - from) * (1 - Math.pow(1 - t, 4));
      if (t < 1) animation.current = requestAnimationFrame(tick); else done?.();
    };
    animation.current = requestAnimationFrame(tick);
  }
  function closeCard() {
    const restore = card && !card.automatic;
    setCard(null); cancelNavigation();
    if (restore) trigger.current?.focus({ preventScroll: true });
  }
  function placeCard(e: Evidence, answerId: string, number: number, automatic: boolean) {
    const target = document.getElementById(e.target);
    const pane = sourcePane.current;
    if (!target || !pane) return;
    const r = target.getBoundingClientRect(), p = pane.getBoundingClientRect();
    const width = Math.min(320, p.width - 32);
    const y = Math.max(52, Math.min(r.bottom - p.top + 10, p.height - 210));
    setCard({ evidence: e, answerId, number, automatic, x: Math.max(16, Math.min(r.left - p.left, p.width - width - 16)), y });
  }
  function locate(e: Evidence, answerId: string, number: number, automatic = false, keyboard = false) {
    setTooltip(null); setPreview(null);
    if (e.status === "unavailable" || e.status === "historical") {
      setNotice(e.status === "historical" ? "这条引用属于历史版本，当前原文不高亮。原型未提供旧版原文。" : "无法在当前原文核对这条引用，因此不会显示高亮。"); return;
    }
    if (!automatic) {
      historyLocked.current = true;
      trigger.current = document.activeElement as HTMLElement;
      setActiveId(answerId);
    }
    setFocused(e.id); setChatHidden(false);
    if (narrow) setMobile("source");
    const token = ++opener.current;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (token !== opener.current) return;
      const el = document.getElementById(e.target), container = source.current;
      if (!el || !container) return;
      const r = el.getBoundingClientRect(), c = container.getBoundingClientRect();
      const visible = r.top >= c.top + 20 && r.bottom <= c.bottom - 30;
      if (!hasReturn) { returnTop.current = container.scrollTop; setHasReturn(true); }
      const done = () => {
        if (token !== opener.current) return;
        placeCard(e, answerId, number, automatic);
        if (keyboard) el.querySelector<HTMLButtonElement>(".cr-source-number")?.focus({ preventScroll: true });
      };
      if (visible) done(); else scrollTo(container, container.scrollTop + r.top - c.top - 64, keyboard, done);
    }));
  }
  function locateSection(id: string) {
    sourceIntent(); setPanel(null); setMobile("source");
    requestAnimationFrame(() => {
      const node = document.getElementById(id), box = source.current;
      if (!node || !box) return;
      returnTop.current = box.scrollTop; setHasReturn(true);
      scrollTo(box, box.scrollTop + node.getBoundingClientRect().top - box.getBoundingClientRect().top - 32, true);
    });
  }
  function backToAnswer(answerId: string, evidenceId?: string, keyboard = false) {
    setMobile("chat"); setChatHidden(false); setCard(null); historyLocked.current = true;
    setActiveId(answerId); if (evidenceId) setFocused(evidenceId);
    following.current = false; setFollow(false);
    requestAnimationFrame(() => {
      const el = document.getElementById(evidenceId ? `claim-${answerId}-${evidenceId}` : `answer-${answerId}`), c = chat.current;
      if (!el || !c) return;
      scrollTo(c, c.scrollTop + el.getBoundingClientRect().top - c.getBoundingClientRect().top - 50, keyboard);
      if (keyboard) el.querySelector<HTMLButtonElement>(".cr-cite")?.focus({ preventScroll: true });
    });
  }
  function showPreview(e: Evidence, target: HTMLElement) {
    setPreview(e.id);
    const rect = target.getBoundingClientRect();
    setTooltip({ text: `${e.label} · ${e.quote}`, x: Math.max(12, Math.min(rect.right - 300, innerWidth - 320)), y: Math.max(16, rect.top - 112) });
  }
  async function send(text = draft, kind = "normal") {
    if (busy || !text.trim()) return;
    const token = ++run.current;
    const id = `a${nextId.current++}`;
    const parts = scriptedAnswer(text, kind);
    const newAnswer: Answer = { id, question: text.trim(), parts, shown: 0, complete: false, quote };
    setAnswers(old => [...old, newAnswer]); setDraft(""); setQuote(""); setSelection(""); setBusy(true);
    setCard(null); setNotice(""); setTooltip(null); setIntroOpen(false);
    manuallyBrowsing.current = false; autoUsed.current = false; historyLocked.current = false; setManual(false);
    following.current = true; setFollow(true); setMobile("chat");
    for (let i = 0; i < parts.length; i++) {
      await new Promise(resolve => setTimeout(resolve, i === 0 ? 850 : 1450));
      if (run.current !== token) return;
      setAnswers(old => old.map(a => a.id === id ? { ...a, shown: i + 1 } : a));
      const e = parts[i].evidence;
      if (e && !["unavailable", "historical"].includes(e.status ?? "")) {
        if (!historyLocked.current) setActiveId(id);
        if (!autoUsed.current) {
          autoUsed.current = true;
          if (!manuallyBrowsing.current && !historyLocked.current && !narrow && document.visibilityState === "visible") {
            locate(e, id, parts.slice(0, i + 1).filter(p => p.evidence).length, true);
          }
        }
      }
    }
    if (run.current !== token) return;
    setAnswers(old => old.map(a => a.id === id ? { ...a, complete: true } : a)); setBusy(false);
  }
  function stop() {
    run.current++; setBusy(false); setAnswers(old => old.map(a => a.complete ? a : { ...a, complete: true, stopped: true }));
    setNotice("回答已停止，已出现的演示证据仍可查看。");
  }
  function reset() {
    run.current++; cancelNavigation(); setBusy(false); setAnswers([]); setActiveId(null); setFocused(null); setCard(null);
    setDraft(""); setQuote(""); setSelection(""); setNotice(""); setManual(false); setHasReturn(false); setIntroOpen(true);
    setPanel(null); setFinished(false); setTooltip(null); historyLocked.current = false; manuallyBrowsing.current = false; autoUsed.current = false;
    source.current?.scrollTo(0, 0); chat.current?.scrollTo(0, 0); following.current = true; setFollow(true);
  }
  function startScenario(value: string) {
    reset(); setScene(value); setIntro(true); setIntroFailed(false);
    const url = new URL(location.href); url.searchParams.set("scene", value); history.replaceState(null, "", url);
    if (value !== "opening") {
      const qs: Record<string, string> = { normal: "为什么重新分配 SRAM 就可能变快？", figure: "结合图和表，解释实验到底支持什么。", block: "切换分区的开销应该怎样理解？", web: "能结合外部资料解释一下吗？", missing: "所以所有模型都能快两倍吗？", historical: "上次回答里的证据还适用于新版吗？" };
      // A scenario loads a completed, inspectable state; ordinary sending demonstrates the streaming sequence.
      const id = `a${nextId.current++}`, parts = scriptedAnswer(qs[value], value);
      setAnswers([{ id, question: qs[value], parts, shown: parts.length, complete: true }]); setActiveId(id); setIntroOpen(false);
      const first = parts.find(p => p.evidence && !["unavailable", "historical"].includes(p.evidence.status ?? ""))?.evidence;
      const scenarioRun = run.current;
      if (first && innerWidth >= 960) setTimeout(() => { if (run.current === scenarioRun) locate(first, id, parts.filter(p => p.evidence).findIndex(p => p.evidence?.id === first.id) + 1, true); }, 80);
    }
  }
  function togglePanel(value: typeof panel, el: HTMLElement) { panelTrigger.current = el; setPanel(panel === value ? null : value); setCard(null); }
  function mark(e: Evidence, content: ReactNode = e.quote) {
    const index = visibleEvidence.findIndex(v => v.id === e.id);
    const enabled = index >= 0;
    return <span id={e.target} className={`cr-evidence-text ${enabled ? "is-evidence" : ""} ${focused === e.id && enabled ? "is-focused" : ""} ${preview === e.id ? "is-preview" : ""}`} data-evidence-active={enabled || undefined}>
      {content}{enabled && <button className="cr-source-number" aria-label={`原文证据 ${index + 1}，回到回答`} onClick={event => activeId && backToAnswer(activeId, e.id, event.detail === 0)}>{index + 1}</button>}
    </span>;
  }
  function objectClass(e: Evidence) { return `cr-object ${validEvidence.some(v => v.id === e.id) ? "is-evidence" : ""} ${focused === e.id ? "is-focused" : ""} ${preview === e.id ? "is-preview" : ""}`; }
  function objectNumber(e: Evidence) {
    const i = visibleEvidence.findIndex(v => v.id === e.id);
    return i < 0 ? null : <button className="cr-source-number cr-object-number" aria-label={`原文证据 ${i + 1}，回到回答`} onClick={event => activeId && backToAnswer(activeId, e.id, event.detail === 0)}>{i + 1}</button>;
  }

  return <div className="cr-app" data-reduce={lowMotion}>
    <header className="cr-header">
      <a href="?scene=opening" className="cr-brand" aria-label="回到阅读原型开场"><span className="cr-logo">F</span><strong>FOCUS</strong></a>
      <span className="cr-header-divider" />
      <div className="cr-source-title">阅读</div>
      <span className="cr-header-spacer" />
      <button onClick={e => togglePanel("contents", e.currentTarget)} aria-label="文章目录" aria-expanded={panel === "contents"}><Icon name="list" /><span>目录</span></button>
      <button onClick={e => togglePanel("notes", e.currentTarget)} aria-label="阅读笔记" aria-expanded={panel === "notes"}><Icon name="bookmark" /><span>笔记{notes.length ? ` ${notes.length}` : ""}</span></button>
      <button onClick={() => setDark(!dark)} aria-label={dark ? "切换浅色" : "切换深色"}><Icon name="sun" /></button>
      <button onClick={e => togglePanel("more", e.currentTarget)} aria-label="更多阅读操作" aria-expanded={panel === "more"}>•••</button>
    </header>
    <nav className="cr-mobile-tabs" aria-label="阅读区域"><button aria-pressed={mobile === "source"} onClick={() => setMobile("source")}>原文</button><button aria-pressed={mobile === "chat"} onClick={() => setMobile("chat")}>对话{validEvidence.length ? ` · ${validEvidence.length} 处依据` : ""}</button></nav>
    <div className="cr-workspace" ref={workspace} data-mobile={mobile} data-chat-hidden={chatHidden} style={{ "--source-ratio": `${ratio}%` } as CSSProperties}>
      <section className="cr-source-pane" ref={sourcePane} aria-label="文章原文">
        <div className="cr-pane-bar"><span>原文</span><button onClick={() => setChatHidden(!chatHidden)} aria-label={chatHidden ? "展开对话" : "收起对话"}>{chatHidden ? "展开对话" : "收起对话"}</button></div>
        <div className="cr-document-scroll" ref={source} tabIndex={0} aria-label="可滚动的完整原文"
          onWheel={sourceIntent} onTouchStart={sourceIntent}
          onKeyDown={e => { if (["PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown", " "].includes(e.key) && !(e.target as HTMLElement).closest("button")) sourceIntent(); }}
          onMouseUp={() => { const s = window.getSelection(); if (s && !s.isCollapsed && source.current?.contains(s.anchorNode) && source.current.contains(s.focusNode)) { sourceIntent(); setSelection(s.toString().trim().slice(0, 600)); } }}>
          <article className="cr-paper">
            <h1>Adaptive SRAM Partitioning<br />for Streaming Accelerators</h1>
            <section id="abstract"><h2>Abstract</h2><p>Streaming accelerators often spend time waiting for data even when their arithmetic units are fast. This article explores a simple question: can the same on-chip memory serve a workload better if its internal partitions change with the computation?</p><p>We describe a phase-aware allocation scheme and an illustrative comparison against fixed partitions. The goal is to explain the relationship between allocation, external traffic, and execution time. All numerical values in this reading sample are synthetic and are included only to demonstrate evidence-linked reading.</p></section>
            <section id="motivation"><h2><span>01</span> Motivation</h2><p>Inputs, weights, and intermediate results do not occupy memory in the same proportions throughout a workload. A phase that reuses many weights may be followed by one that needs more space for intermediate values.</p><p>{mark(evidence.traffic)} The capacity exists, but it is unavailable to the data class that needs it. Increasing arithmetic throughput alone does not resolve this mismatch.</p><p className={highlight ? "cr-user-highlight" : ""}>The useful question is not only how much memory is present, but how much of it is available to the active computation.</p><p>A balanced fixed allocation is a reasonable baseline, yet it cannot adapt to every phase. To make a fair comparison, capacity and compute resources must be held constant while the allocation policy changes.</p></section>
            <section id="method"><h2><span>02</span> Phase-aware partitioning</h2><p>{mark(evidence.capacity)} A controller selects a partition from a small set of legal layouts. It uses the expected working set of the next phase rather than changing the allocation every cycle.</p><p>{mark(evidence.boundary)} This boundary makes ownership easier to reason about. A transfer must never write into a region that has already been reassigned.</p>
              <figure id="ev-figure" className={objectClass(evidence.figure)}>{objectNumber(evidence.figure)}<div className="cr-diagram"><div className="cr-diagram-title">ONE SRAM · TWO ALLOCATIONS</div><div className="cr-memory-row"><span>Phase A</span><div><i style={{ flex: 2 }}>Inputs</i><i style={{ flex: 5 }}>Weights</i><i style={{ flex: 3 }}>Results</i></div></div><div className="cr-diagram-arrow">↓ &nbsp; drain transfers → reconfigure</div><div className="cr-memory-row"><span>Phase B</span><div><i style={{ flex: 4 }}>Inputs</i><i style={{ flex: 2 }}>Weights</i><i style={{ flex: 4 }}>Results</i></div></div><div className="cr-diagram-footer">Same total capacity. Different working sets.</div></div><figcaption><strong>Figure 1.</strong> The same SRAM is allocated differently across compute phases.</figcaption></figure>
              <p>The controller chooses a layout only when the predicted reduction in external transfers can offset the transition cost. A minimal decision rule is:</p><div className="cr-equation" aria-label="saved memory time must exceed transition time">T<sub>saved memory</sub> &gt; T<sub>drain</sub> + T<sub>reconfigure</sub></div><p>This inequality is a scheduling condition, not a guarantee that every phase benefits. When the condition is not met, the controller keeps the current partition.</p></section>
            <section id="evaluation"><h2><span>03</span> Controlled evaluation</h2><p>The illustrative experiment holds total SRAM capacity, compute throughput, and external bandwidth constant. It compares a balanced fixed layout, a weight-heavy fixed layout, and a phase-aware layout. Values are normalized to the balanced baseline.</p>
              <figure id="ev-table" className={objectClass(evidence.table)}>{objectNumber(evidence.table)}<div className="cr-table-wrap"><table><thead><tr><th>Allocation</th><th>External traffic</th><th>Cycles</th></tr></thead><tbody><tr><td>Fixed balanced</td><td>1.00</td><td>1.00</td></tr><tr><td>Fixed weight-heavy</td><td>0.91</td><td>0.95</td></tr><tr><td>Adaptive</td><td>0.72</td><td>0.84</td></tr></tbody></table></div><figcaption><strong>Table 1.</strong> Synthetic values for this interface prototype. Lower is better; no physical chip measurements are represented.</figcaption></figure>
              <p>Reduced traffic and reduced cycles are related but not interchangeable. The cycle result includes the transition cost in the simulator. A claim about energy would require an additional measurement or model that is not provided here.</p></section>
            <section id="limitations"><h2><span>04</span> Limitations</h2><p>{mark(evidence.limit)} Real systems include software scheduling, interconnect contention, and variability that are absent from this simplified comparison.</p><div id="ev-block" className={`cr-block-evidence ${validEvidence.some(e => e.id === "block") ? "is-evidence" : ""} ${preview === "block" ? "is-preview" : ""}`}><p>Scheduling and transfer costs must be evaluated together. An allocation that reduces external bytes can still be slower if it causes frequent transitions. Prediction errors can also make the selected partition worse than a fixed layout.</p>{objectNumber(evidence.block)}</div><p>A broader study should vary workload phases, capacity constraints, and memory bandwidth independently. Cases with little benefit or a slowdown should remain in the report rather than being filtered out.</p></section>
            <section id="conclusion"><h2><span>05</span> Conclusion</h2><p>Phase-aware partitioning changes where capacity is available without increasing its total size. The central tradeoff is between external memory traffic and the cost of changing layouts. Reading the allocation rule together with the experimental conditions is necessary to understand what a result does—and does not—support.</p></section>
            <div className="cr-end"><button onClick={() => setFinished(!finished)}>{finished ? "✓ 已标记读完 · 撤销" : "标记读完"}</button></div>
          </article>
        </div>
        {(hasReturn || (narrow && activeId)) && <div className="cr-return-bar">{hasReturn && <button onClick={() => { cancelNavigation(); source.current?.scrollTo({ top: returnTop.current, behavior: "instant" }); setCard(null); setHasReturn(false); }}><Icon name="return" size={15} />返回刚才位置</button>}{narrow && activeId && <button onClick={() => backToAnswer(activeId)}>返回回答 →</button>}</div>}
        {selection && <div className="cr-selection"><span>已选 {selection.length} 字</span><button onClick={() => { setQuote(selection); setSelection(""); setMobile("chat"); setChatHidden(false); window.getSelection()?.removeAllRanges(); requestAnimationFrame(() => composer.current?.focus()); }}>问这段 <Icon name="chat" size={15} /></button></div>}
        {renderedCard && <aside className="cr-evidence-card" role="region" aria-label="原文证据详情" aria-hidden={!cardOpen} inert={!cardOpen} data-open={cardOpen} style={{ left: renderedCard.x, top: renderedCard.y }}>
          <header><span className="cr-card-number">{renderedCard.number}</span><strong>{renderedCard.evidence.status === "block" ? "段落定位" : "本轮证据"}</strong><button aria-label="关闭证据详情" onClick={closeCard}><Icon name="close" size={15} /></button></header>
          <small>{renderedCard.evidence.label}</small><p>{renderedCard.evidence.claim}</p><button className="cr-text-link" onClick={e => backToAnswer(renderedCard.answerId, renderedCard.evidence.id, e.detail === 0)}>查看关联回答 <span>↗</span></button>
        </aside>}
      </section>
      <div className="cr-divider" role="separator" tabIndex={0} aria-label="调整原文和对话宽度" aria-orientation="vertical" aria-valuemin={45} aria-valuemax={70} aria-valuenow={Math.round(ratio)}
        onKeyDown={e => { if (["ArrowLeft", "ArrowRight", "Home"].includes(e.key)) { e.preventDefault(); setRatio(e.key === "Home" ? 60 : Math.max(45, Math.min(70, ratio + (e.key === "ArrowLeft" ? -2 : 2)))); setCard(null); } }}
        onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); setCard(null); cancelNavigation(); }}
        onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId) || !workspace.current) return; const r = workspace.current.getBoundingClientRect(); setRatio(Math.max(45, Math.min(70, 100 * (e.clientX - r.left) / r.width))); }}
        onPointerUp={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); }}><i /></div>
      <section className="cr-chat-pane" aria-label="文章对话">
        <div className="cr-pane-bar"><span>对话</span>{intro && introOpen && <button onClick={() => setIntroOpen(false)} aria-expanded={true}>收起导读</button>}</div>
        <div className="cr-chat-scroll" ref={chat} tabIndex={0} aria-label="可滚动的讨论历史" onWheel={e => { if (e.deltaY < 0) { following.current = false; setFollow(false); } }} onTouchStart={() => { following.current = false; setFollow(false); }} onKeyDown={e => { if (["PageUp", "Home", "ArrowUp"].includes(e.key)) { following.current = false; setFollow(false); } }} onScroll={() => { if (chat.current) { const atBottom = chat.current.scrollHeight - chat.current.scrollTop - chat.current.clientHeight < 48; following.current = atBottom; setFollow(atBottom); } }}>
          <section className="cr-opening">
            {!intro ? <p role="status">正在生成导读…</p> : introFailed ? <div role="status"><p>导读生成失败。</p><button onClick={() => { setIntroFailed(false); setIntro(false); setTimeout(() => setIntro(true), 650); }}>重试</button></div> : introOpen ? <>
              <div className="cr-skeleton">{sections.map((s, i) => <button key={s.id} onClick={() => locateSection(s.id)}><span>{String(i + 1).padStart(2, "0")}</span><div><strong>{s.label}</strong></div><span className="cr-node-arrow">↗</span></button>)}</div>
              <p className="cr-guide">{guide}</p>
            </> : <button className="cr-opening-summary" onClick={() => setIntroOpen(true)} aria-expanded={false}>骨架与导读</button>}
          </section>
          {answers.map(a => <div className="cr-turn" key={a.id}>
            <div className="cr-question">{a.quote && <blockquote>{a.quote}</blockquote>}{a.question}</div>
            <article id={`answer-${a.id}`} className={`cr-answer ${activeId === a.id ? "is-selected" : ""}`} aria-label={`回答：${a.question}`}>
              <div className="cr-answer-heading"><span className="cr-mini-logo" aria-label="模型回答">F</span>{!a.complete && <small>正在回答…</small>}</div>
              {a.shown === 0 && <p className="cr-generating" role="status">正在阅读相关内容…</p>}
              {a.parts.slice(0, a.shown).map((p, i) => {
                const e = p.evidence, number = a.parts.slice(0, i + 1).filter(part => part.evidence).length;
                return <div key={i} id={e ? `claim-${a.id}-${e.id}` : undefined} className={`cr-claim ${focused === e?.id && activeId === a.id ? "is-focused" : ""}`}>
                  <p>{p.text}{e && <button className={`cr-cite ${e.status === "unavailable" || e.status === "historical" ? "is-unavailable" : ""}`} aria-label={`证据 ${number}，${e.label}，定位原文`} onMouseEnter={event => showPreview(e, event.currentTarget)} onMouseLeave={() => { setPreview(null); setTooltip(null); }} onFocus={event => showPreview(e, event.currentTarget)} onBlur={() => { setPreview(null); setTooltip(null); }} onClick={event => locate(e, a.id, number, false, event.detail === 0)}>{number}{e.status === "unavailable" || e.status === "historical" ? "!" : ""}</button>}</p>
                  {e?.status && <span className="cr-resolution">{e.status === "block" ? "段落定位" : e.status === "historical" ? "历史版本 · 当前原文不高亮" : "未核对到原文 · 不显示高亮"}</span>}
                  {p.external && <a className="cr-external" href="https://en.wikipedia.org/wiki/Memory_hierarchy" target="_blank" rel="noreferrer"><span>↗</span><div><strong>Memory hierarchy</strong><small>外部链接示例 · 非实时检索结果</small></div></a>}
                </div>;
              })}
              {a.complete && <div className="cr-answer-actions"><button onClick={() => { historyLocked.current = true; setActiveId(a.id); setCard(null); setFocused(null); }}>查看证据 · {a.parts.slice(0, a.shown).filter(p => p.evidence && !["unavailable", "historical"].includes(p.evidence.status ?? "")).length}</button><button onClick={() => { setNotes(old => [...old, a.parts.slice(0, a.shown).map(p => p.text).join("\n")]); setNotice("已存入原型笔记，刷新后清空。"); }}>记笔记</button>{a.stopped && <small>已停止 · 回答不完整</small>}</div>}
            </article>
          </div>)}
          <div className="cr-chat-end" />
        </div>
        {!follow && !!answers.length && <button className="cr-latest" onClick={() => { following.current = true; setFollow(true); if (chat.current) chat.current.scrollTop = chat.current.scrollHeight; }}>回到最新 ↓</button>}
        <div className="cr-compose-wrap">
          {active && <div className="cr-evidence-summary"><span>{validEvidence.length ? `本轮 ${validEvidence.length} 处原文依据` : "本轮暂无可定位原文"}</span>{manual && <small>跟随已暂停</small>}{validEvidence[0] && <button onClick={() => locate(validEvidence[0], active.id, visibleEvidence.indexOf(validEvidence[0]) + 1)}>查看原文 ↗</button>}</div>}
          <form className="cr-composer" onSubmit={e => { e.preventDefault(); void send(); }}>
            {quote && <div className="cr-quote"><span>{quote}</span><button type="button" aria-label="移除选文引用" onClick={() => setQuote("")}><Icon name="close" size={14} /></button></div>}
            <textarea ref={composer} aria-label="围绕文章提问" placeholder="输入消息…" value={draft} onChange={e => setDraft(e.target.value)} rows={2} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); void send(); } }} />
            <div className="cr-compose-bottom">{busy ? <button type="button" className="cr-send" aria-label="停止回答" onClick={stop}>■</button> : <button className="cr-send" type="submit" aria-label="发送问题" disabled={!draft.trim()}><Icon name="up" size={18} /></button>}</div>
          </form>
        </div>
      </section>
    </div>
    {panel && <><button className="cr-panel-scrim" aria-label="关闭阅读面板" onClick={() => { setPanel(null); panelTrigger.current?.focus(); }} /><aside className="cr-panel" aria-label={panel === "contents" ? "文章目录" : panel === "notes" ? "阅读笔记" : "更多操作"}>
      <header><strong>{panel === "contents" ? "文章目录" : panel === "notes" ? "阅读笔记" : "更多操作"}</strong><button aria-label="关闭阅读面板" onClick={() => { setPanel(null); panelTrigger.current?.focus(); }}><Icon name="close" /></button></header>
      {panel === "contents" && sections.map((s, i) => <button className="cr-panel-row" key={s.id} onClick={() => locateSection(s.id)}><span>0{i + 1}</span><div>{s.label}<small>{s.en}</small></div>↗</button>)}
      {panel === "notes" && <><button className="cr-panel-row" onClick={() => setHighlight(!highlight)}><Icon name="bookmark" />{highlight ? "隐藏样文中的用户重点" : "显示样文中的用户重点"}</button>{notes.length ? notes.map((n, i) => <div className="cr-saved-note" key={i}><small>整篇笔记 · 本次原型</small><p>{n}</p><button onClick={() => setNotes(old => old.filter((_, j) => i !== j))}>删除</button></div>) : <p className="cr-panel-note">暂无笔记</p>}</>}
      {panel === "more" && <><button className="cr-panel-row" onClick={() => { setIntroOpen(true); setPanel(null); setMobile("chat"); setChatHidden(false); chat.current?.scrollTo(0, 0); }}>查看中文骨架与导读 ↗</button><button className="cr-panel-row" onClick={() => { setFinished(!finished); setNotice(finished ? "已撤销读完标记。" : "已标记读完。"); }}>{finished ? "撤销读完标记" : "标记读完"}</button><button className="cr-panel-row" onClick={() => { setPanel(null); setIntroFailed(true); setIntro(true); setIntroOpen(true); chat.current?.scrollTo(0, 0); }}>演示开场准备失败</button></>}
    </aside></>}
    {tooltip && <div className="cr-tooltip" role="tooltip" style={{ left: tooltip.x, top: tooltip.y }}>{tooltip.text}</div>}
    {notice && <div className="cr-notice" role="status"><span>{notice}</span><button aria-label="关闭提示" onClick={() => setNotice("")}><Icon name="close" size={15} /></button></div>}
    <footer className="cr-demo-bar"><details className="cr-demo-controls"><summary>原型</summary><div>
      <label>场景<select aria-label="切换演示场景" value={scene} onChange={e => startScenario(e.target.value)}>{Object.entries(scenarioLabels).map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select></label>
      <button onClick={() => startScenario("opening")}>重新体验</button>
      <label><input type="checkbox" checked={reduce} onChange={e => setReduce(e.target.checked)} />减少动效</label>
      <p>合成样文与预设回答，未接入模型。</p>
    </div></details></footer>
    <span className="cr-sr-only" role="status" aria-live="polite">{busy ? "正在生成演示回答" : `${validEvidence.length} 处可定位的原文证据`}</span>
  </div>;
}

const root = createRoot(document.getElementById("root")!);
root.render(<Prototype />);
const hot = (import.meta as ImportMeta & { hot?: { dispose(callback: () => void): void } }).hot;
hot?.dispose(() => root.unmount());
