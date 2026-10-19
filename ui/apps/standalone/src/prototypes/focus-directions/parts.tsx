import { createContext, useContext, useLayoutEffect, useRef, useState } from "react";
import { MarkdownContent } from "../../../../../packages/reader-ui/src/MarkdownContent";
import { figures, units, type FigureRef, type Message, type Unit } from "./data";
import type { Demo, Entry } from "./engine";

export type ReaderCtx = {
  demo: Demo;
  focusUnit: number;
  reviewing: boolean;
  quote: (unit: number, excerpt?: string) => void;
  openFigure: (figure: FigureRef, origin: HTMLElement) => void;
  pinFigure: (figure: FigureRef) => void;
  jumpToSource: (unit: number, quote?: string) => void;
  saveNote: (unit: number, text: string) => void;
  linkQuote: (unit: number, quote: string | null) => void;
  fresh: (key: string) => boolean;
  split: boolean;
};
export const Ctx = createContext<ReaderCtx>(null!);

function useEnter(key: string) {
  const ctx = useContext(Ctx);
  const [on] = useState(() => ctx.fresh(key));
  return on ? "true" : undefined;
}

export type Group = { unit: number | null; msgs: Message[]; key: string };
export function groupByUnit(timeline: Entry[], messages: Record<string, Message>): Group[] {
  const out: Group[] = [];
  for (const e of timeline) {
    if (e.kind === "unit") { out.push({ unit: e.index, msgs: [], key: `u${e.index}` }); continue; }
    const m = messages[e.id]; if (!m) continue;
    const home = [...out].reverse().find(g => g.unit === m.unit);
    if (home) home.msgs.push(m);
    else if (out.at(-1)?.unit === null) out.at(-1)!.msgs.push(m);
    else out.push({ unit: null, msgs: [m], key: `o${m.id}` });
  }
  return out;
}
export function chronological(timeline: Entry[], messages: Record<string, Message>): Group[] {
  const out: Group[] = [];
  for (const e of timeline) {
    if (e.kind === "unit") { out.push({ unit: e.index, msgs: [], key: `u${e.index}` }); continue; }
    const m = messages[e.id]; if (!m) continue;
    if (out.length) out.at(-1)!.msgs.push(m); else out.push({ unit: null, msgs: [m], key: `o${m.id}` });
  }
  return out;
}

export function UnitHead({ unit, compact }: { unit: Unit; compact?: boolean }) {
  const ctx = useContext(Ctx);
  const isFrontier = unit.index === ctx.demo.frontier;
  return <header className="fd-unit-head">
    <div className="fd-meta">
      <span className="fd-idx">{String(unit.index).padStart(2, "0")}</span>
      <span className="fd-path">{unit.section}</span>
      {isFrontier && <span className="fd-frontier" title="正式阅读进度停在这一段">当前进度</span>}
      <span className="fd-grow" />
      <span className="fd-unit-tools">
        <button className="fd-ghost fd-sm" onClick={() => ctx.quote(unit.index)}>引用提问</button>
        {!compact && <button className="fd-ghost fd-sm" title="演示：原文/译文切换不改变阅读位置">原文</button>}
      </span>
    </div>
    <h2 className="fd-unit-title">{unit.title}</h2>
  </header>;
}

export function SourceText({ unit }: { unit: Unit }) {
  return <div className="fd-prose" data-source-text={unit.index}><MarkdownContent text={unit.body} /></div>;
}

export function FigureStrip({ unit }: { unit: Unit }) {
  const ctx = useContext(Ctx);
  if (!unit.figures.length) return null;
  return <div className="fd-figstrip">
    {unit.figures.map(id => {
      const f = figures[id];
      return <div className="fd-figchip" key={id}>
        <button className="fd-figthumb" data-fig-origin={id} aria-label={`放大${f.label}`} onClick={e => ctx.openFigure(f, e.currentTarget)}>
          <img src={f.src} alt="" />
        </button>
        <div className="fd-figtext">
          <strong>{f.label}</strong><span>{f.caption.replace(/^图 \d：/, "")}</span>
          <button className="fd-link" onClick={() => ctx.pinFigure(f)}>在资料栏固定</button>
        </div>
      </div>;
    })}
  </div>;
}

export function Question({ m }: { m: Message }) {
  const ctx = useContext(Ctx);
  const enter = useEnter(m.id);
  return <div className="fd-q" data-msg={m.id} data-enter={enter}>
    {m.quote && <button className="fd-quote" onClick={() => ctx.jumpToSource(m.unit, m.quote)}
      onMouseEnter={() => ctx.linkQuote(m.unit, m.quote ?? null)} onMouseLeave={() => ctx.linkQuote(m.unit, null)}
      title="回看原文中的这句话">
      <span className="fd-quote-mark">第 {m.unit} 段</span><span className="fd-quote-text">{m.quote}</span>
    </button>}
    <p>{m.text}</p>
  </div>;
}

export function Answer({ m }: { m: Message }) {
  const ctx = useContext(Ctx);
  const enter = useEnter(m.id);
  const f = m.figure ? figures[m.figure] : null;
  const [copied, setCopied] = useState(false);
  return <div className="fd-a" data-msg={m.id} data-enter={enter} data-streaming={m.streaming ? "true" : undefined}>
    <div className="fd-a-head"><span className="fd-a-who">FOCUS</span><span className="fd-demo-tag">演示回复</span>{m.streaming && <span className="fd-a-state">生成中</span>}</div>
    <div className="fd-a-body"><MarkdownContent text={m.text || " "} />{m.streaming && <span className="fd-caret" aria-hidden="true" />}</div>
    {f && <button className="fd-a-fig" data-fig-origin={`${m.id}-${f.id}`} onClick={e => ctx.openFigure(f, e.currentTarget)}>
      <img src={f.src} alt={f.caption} /><span>{f.label} · 点击放大</span>
    </button>}
    {!m.streaming && <div className="fd-a-actions">
      <button className="fd-ghost fd-sm" onClick={() => ctx.saveNote(m.unit, m.text.split("\n")[0].replace(/[#*$]/g, "").slice(0, 80))}>存为笔记</button>
      <button className="fd-ghost fd-sm" onClick={() => { void navigator.clipboard?.writeText(m.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1600); }, () => {}); }}>{copied ? "已复制" : "复制"}</button>
      <button className="fd-ghost fd-sm" onClick={() => ctx.jumpToSource(m.unit)}>回看第 {m.unit} 段</button>
    </div>}
  </div>;
}

function Thread({ msgs }: { msgs: Message[] }) {
  return <>{msgs.map(m => m.role === "user" ? <Question key={m.id} m={m} /> : <Answer key={m.id} m={m} />)}</>;
}

/* ───────────── A · 聚光卡片：段落 + 讨论组成一张卡，当前卡片浮起，历史卡片沉入纸面 ───────────── */
function CardA({ group }: { group: Group }) {
  const ctx = useContext(Ctx);
  const enter = useEnter(group.key);
  if (group.unit === null) return <section className="a-card a-orphan" data-state="near"><div className="a-thread"><Thread msgs={group.msgs} /></div></section>;
  const unit = units[group.unit - 1];
  const dist = Math.abs(unit.index - ctx.focusUnit);
  return <article className="a-card" data-unit={unit.index} data-landing data-enter={enter}
    data-state={dist === 0 ? "focus" : dist === 1 ? "near" : "far"} data-review={dist === 0 && ctx.reviewing ? "true" : undefined}>
    <UnitHead unit={unit} />
    <SourceText unit={unit} />
    <FigureStrip unit={unit} />
    {group.msgs.length > 0 && <div className="a-thread"><Thread msgs={group.msgs} /></div>}
  </article>;
}
export function TimelineA({ groups }: { groups: Group[] }) {
  return <div className="a-stack">{groups.map(g => <CardA key={g.key} group={g} />)}</div>;
}

/* ───────────── A+B · 选定方案：A 的卡片与渐进隐退；宽屏且资料关闭时，讨论移到卡片右栏并吸附 ───────────── */
function CardAB({ group }: { group: Group }) {
  const ctx = useContext(Ctx);
  const enter = useEnter(group.key);
  if (group.unit === null) return <section className="a-card a-orphan" data-state="near"><div className="a-thread"><Thread msgs={group.msgs} /></div></section>;
  const unit = units[group.unit - 1];
  const dist = Math.abs(unit.index - ctx.focusUnit);
  return <article className="a-card ab-card" data-unit={unit.index} data-landing data-enter={enter}
    data-state={dist === 0 ? "focus" : dist === 1 ? "near" : "far"} data-review={dist === 0 && ctx.reviewing ? "true" : undefined}>
    <div className="ab-src"><UnitHead unit={unit} /><SourceText unit={unit} /><FigureStrip unit={unit} /></div>
    <aside className="ab-side" key={String(ctx.split)} aria-label={`第 ${unit.index} 段的讨论`}>
      {group.msgs.length ? <Thread msgs={group.msgs} /> : <button className="b-ask" onClick={() => ctx.quote(unit.index)}><span>＋</span> 就这段提问</button>}
    </aside>
  </article>;
}
export function TimelineAB({ groups }: { groups: Group[] }) {
  return <div className="a-stack">{groups.map(g => <CardAB key={g.key} group={g} />)}</div>;
}

/* ───────────── B · 原文旁注：原文为主轴，讨论与它所在段落并排 ───────────── */
function RowB({ group }: { group: Group }) {
  const ctx = useContext(Ctx);
  const enter = useEnter(group.key);
  if (group.unit === null) return <section className="b-row b-orphan"><div className="b-src" /><aside className="b-side"><Thread msgs={group.msgs} /></aside></section>;
  const unit = units[group.unit - 1];
  const dist = Math.abs(unit.index - ctx.focusUnit);
  return <section className="b-row" data-unit={unit.index} data-landing data-enter={enter} data-state={dist === 0 ? "focus" : dist === 1 ? "near" : "far"}>
    <div className="b-src"><UnitHead unit={unit} compact /><SourceText unit={unit} /><FigureStrip unit={unit} /></div>
    <aside className="b-side" aria-label={`第 ${unit.index} 段的讨论`}>
      {group.msgs.length ? <Thread msgs={group.msgs} /> : <button className="b-ask" onClick={() => ctx.quote(unit.index)}><span>＋</span> 就这段提问</button>}
    </aside>
  </section>;
}
export function TimelineB({ groups }: { groups: Group[] }) {
  return <div className="b-sheet">{groups.map(g => <RowB key={g.key} group={g} />)}</div>;
}

/* ───────────── C · 阅读光标：连续文档 + 一块随视线移动的“光标面板” ───────────── */
function GroupC({ group }: { group: Group }) {
  const ctx = useContext(Ctx);
  const enter = useEnter(group.key);
  if (group.unit === null) return <section className="c-group" data-enter={enter}><div className="c-msgs"><Thread msgs={group.msgs} /></div></section>;
  const unit = units[group.unit - 1];
  const dist = Math.abs(unit.index - ctx.focusUnit);
  return <section className="c-group" data-unit={unit.index} data-landing data-enter={enter} data-state={dist === 0 ? "focus" : dist === 1 ? "near" : "far"}>
    <UnitHead unit={unit} />
    <SourceText unit={unit} />
    <FigureStrip unit={unit} />
    {group.msgs.length > 0 && <div className="c-msgs"><Thread msgs={group.msgs} /></div>}
  </section>;
}
export function TimelineC({ groups }: { groups: Group[] }) {
  const ctx = useContext(Ctx);
  const doc = useRef<HTMLDivElement>(null);
  const lens = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const root = doc.current, el = lens.current; if (!root || !el) return;
    const place = () => {
      const target = root.querySelector<HTMLElement>(`.c-group[data-unit="${ctx.focusUnit}"]`);
      if (!target) { el.style.opacity = "0"; return; }
      el.style.opacity = "1";
      el.style.transform = `translateY(${target.offsetTop - 18}px)`;
      el.style.height = `${target.offsetHeight + 36}px`;
    };
    place();
    const ro = new ResizeObserver(place); ro.observe(root);
    return () => ro.disconnect();
  }, [ctx.focusUnit, groups.length]);
  return <div className="c-doc" ref={doc}>
    <div className="c-lens" ref={lens} data-review={ctx.reviewing ? "true" : undefined} aria-hidden="true" />
    {groups.map(g => <GroupC key={g.key} group={g} />)}
  </div>;
}