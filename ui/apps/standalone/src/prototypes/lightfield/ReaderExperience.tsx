import { cursorReceipt, type ReaderChunk, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { type FormEvent, type PointerEvent as ReactPointerEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Direction } from "./variants";
import { Icon, Emblem } from "./icons";

const scenes = {
  mist: { number: "01", english: "SOFT FOCUS", line: "让注意力，轻轻落在此刻。", label: "雾光", intensity: 65, particles: false },
  folio: { number: "02", english: "THE QUIET PAGE", line: "给一个想法，留一整页空白。", label: "留白", intensity: 35, particles: false },
  nocturne: { number: "03", english: "AFTER HOURS", line: "世界安静下来，思绪开始发光。", label: "极夜", intensity: 75, particles: true },
  current: { number: "04", english: "A THREAD OF THOUGHT", line: "每一次追问，都是思路的延长。", label: "流动", intensity: 45, particles: false },
  duet: { number: "05", english: "SIDE BY SIDE", line: "一边是文字，一边是新的理解。", label: "共读", intensity: 55, particles: false },
};

function reducedMotion() { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
function number(value: number) { return String(value).padStart(2, "0"); }

export function ReaderExperience({ host, direction }: { host: ReaderHost; direction: Direction }) {
  const scene = scenes[direction];
  const [reading, setReading] = useState<ReadingWindow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [intensity, setIntensity] = useState(scene.intensity);
  const [particles, setParticles] = useState(scene.particles);
  const [focus, setFocus] = useState(false);
  const [largeText, setLargeText] = useState(false);
  const [draft, setDraft] = useState("");
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [bookmarks, setBookmarks] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState<"source" | "contents" | null>(null);
  const [mobileChat, setMobileChat] = useState(false);
  const stream = useRef<HTMLDivElement>(null);
  const chat = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const operation = useRef(false);
  const mounted = useRef(true);
  const firstLanding = useRef(true);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);

  useEffect(() => {
    mounted.current = true;
    void host.getReadingWindow().then((result) => {
      if (!mounted.current) return;
      if (result.ok) setReading(result.value);
      else setError(result.error.message);
    });
    return () => { mounted.current = false; if (toastTimer.current) clearTimeout(toastTimer.current); };
  }, [host]);

  const current = reading?.current;
  const chunks = reading ? [...reading.history, ...(current ? [current] : [])] : [];
  const active = current ?? chunks.at(-1);
  const total = active?.total ?? 8;
  const progress = reading?.status === "completed" ? total : (current?.index ?? 1) - 1;
  const conversation = (reading?.conversation ?? []).filter((message) =>
    message.chunkId === active?.chunkId && !message.messageId.startsWith("reading-"));
  const displayChunk = chunks.find((chunk) => chunk.chunkId === reviewing) ?? active;

  function centerChunk(id?: string, smooth = true) {
    const pane = stream.current;
    const element = id ? pane?.querySelector<HTMLElement>(`[data-chunk-id="${id}"]`) : pane?.querySelector<HTMLElement>(".lf-completed");
    if (!pane || !element) return;
    const paneRect = pane.getBoundingClientRect();
    const rect = element.getBoundingClientRect();
    const target = pane.scrollTop + rect.top - paneRect.top - Math.max(32, (pane.clientHeight - rect.height) / 2);
    pane.scrollTo({ top: target, behavior: smooth && !reducedMotion() ? "smooth" : "instant" });
  }

  useLayoutEffect(() => {
    if (!reading) return;
    const frame = requestAnimationFrame(() => {
      centerChunk(current?.chunkId, !firstLanding.current);
      firstLanding.current = false;
    });
    return () => cancelAnimationFrame(frame);
  }, [current?.chunkId, reading?.status]);

  useEffect(() => {
    const resize = () => centerChunk(reviewing ?? current?.chunkId, false);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [current?.chunkId, reviewing]);

  useLayoutEffect(() => {
    if (chat.current) chat.current.scrollTo({ top: chat.current.scrollHeight, behavior: reducedMotion() ? "instant" : "smooth" });
  }, [conversation.length, active?.chunkId]);

  useEffect(() => {
    if (modal) dialog.current?.showModal();
    else if (dialog.current?.open) dialog.current.close();
  }, [modal]);

  function toast(message: string) {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setNotice(message);
    toastTimer.current = setTimeout(() => setNotice(""), 2800);
  }

  async function advance() {
    if (!reading || operation.current || !current) return;
    const receipt = cursorReceipt(reading);
    if (!receipt) return;
    operation.current = true;
    setBusy(true); setError(""); setReviewing(null);
    const result = await host.continueReading({ receipt });
    operation.current = false;
    if (!mounted.current) return;
    setBusy(false);
    if (result.ok) {
      setReading(result.value);
      setDraft("");
    } else setError(result.error.message);
  }

  async function ask(content = draft) {
    if (!reading || operation.current || !content.trim()) return;
    const receipt = cursorReceipt(reading);
    if (!receipt) return;
    operation.current = true;
    setBusy(true); setError("");
    const result = await host.sendMessage({ receipt, content });
    operation.current = false;
    if (!mounted.current) return;
    setBusy(false);
    if (result.ok) { setReading(result.value); setDraft(""); }
    else setError(result.error.message);
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(target.tagName) || target.isContentEditable || event.ctrlKey || event.metaKey || event.altKey || document.querySelector("dialog[open]")) return;
      if (event.code === "Space" && !event.repeat) { event.preventDefault(); void advance(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [reading]);

  function showModal(value: "source" | "contents") {
    lastTrigger.current = document.activeElement as HTMLElement;
    setModal(value);
  }

  function review(chunk: ReaderChunk) {
    setReviewing(chunk.chunkId === current?.chunkId ? null : chunk.chunkId);
    centerChunk(chunk.chunkId);
    setModal(null);
  }

  function toggleBookmark() {
    if (!displayChunk) return;
    const saved = bookmarks.includes(displayChunk.chunkId);
    setBookmarks((previous) => saved ? previous.filter((id) => id !== displayChunk.chunkId) : [...previous, displayChunk.chunkId]);
    toast(saved ? "已取消标记" : "已标记这一段 · 仅在本轮演示中保留");
  }

  function submit(event: FormEvent) { event.preventDefault(); void ask(); }

  function adjustLight(event: ReactPointerEvent<HTMLInputElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    setIntensity(Math.max(0, Math.min(100, Math.round((event.clientX - rect.left - 7) / (rect.width - 14) * 100))));
  }

  return <div className={`lf-app lf-${direction}`} data-focus={focus} data-large={largeText} data-mobile-chat={mobileChat}>
    <div className="lf-atmosphere" aria-hidden="true" style={{ opacity: intensity / 100 }}>
      <div className="lf-light lf-light-a" /><div className="lf-light lf-light-b" /><div className="lf-light lf-light-c" />
      {direction === "nocturne" && <div className="lf-orbit" />}
    </div>
    <div className="lf-grain" aria-hidden="true" />
    {particles && <div className="lf-particles" aria-hidden="true">{Array.from({ length: 32 }, (_, index) => <i key={index} style={{ left: `${(index * 37 + 7) % 100}%`, top: `${(index * 23 + 11) % 100}%`, animationDelay: `${-index * 1.7}s`, animationDuration: `${18 + index % 5 * 4}s`, width: index % 4 === 0 ? 3 : 2, height: index % 4 === 0 ? 3 : 2 }} />)}</div>}

    <header className="lf-header">
      <a className="lf-brand" href="#" onClick={(event) => { event.preventDefault(); centerChunk(current?.chunkId); setReviewing(null); }} aria-label="FOCUS 回到当前阅读位置">
        <Emblem /><span>focus<span className="lf-brand-dot">.</span></span><span className="lf-brand-divider" /><span className="lf-brand-sub">留一点时间，给思考</span>
      </a>
      <button className="lf-source-breadcrumb" onClick={() => showModal("contents")} title="查看阅读目录"><span>私人阅读空间</span><Icon name="chevron" size={12} /><span>安静系统</span></button>
      <div className="lf-header-actions">
        <span className="lf-demo-label"><i />交互原型</span>
        <button className="lf-icon-button" aria-label="阅读目录" title="阅读目录" onClick={() => showModal("contents")}><Icon name="list" /></button>
        <button className="lf-icon-button" aria-label={focus ? "退出专注模式" : "专注模式"} aria-pressed={focus} title="专注模式" onClick={() => { setFocus(!focus); requestAnimationFrame(() => centerChunk(current?.chunkId, false)); }}><Icon name="focus" /></button>
        <button className="lf-avatar" title="本地演示，未连接真实账户" onClick={() => toast("私人阅读空间 · 本地演示，未连接账户")}>Y</button>
      </div>
    </header>

    <div className="lf-workspace">
      <aside className="lf-rail" aria-label="Chunk 阅读进度">
        <span className="lf-rail-caption">READING<br />JOURNEY</span>
        <div className="lf-track">
          <div className="lf-track-line" />
          <div className="lf-track-done" style={{ transform: `scaleY(${Math.min(progress / (total - 1), 1)})` }} />
          {Array.from({ length: total }, (_, index) => {
            const chunk = chunks[index];
            const isCurrent = index + 1 === current?.index;
            return <button key={index} className="lf-track-step" data-done={index < progress} data-current={isCurrent} disabled={!chunk}
              title={chunk ? `回看 ${number(index + 1)} · ${chunk.sectionPath.at(-1)}` : `第 ${number(index + 1)} 段 · 尚未阅读`}
              aria-label={`第 ${index + 1} 段${isCurrent ? "，当前位置" : index < progress ? "，已读，可回看" : "，尚未阅读"}`}
              aria-current={isCurrent ? "step" : undefined} style={{ top: `${index / (total - 1) * 100}%` }} onClick={() => chunk && review(chunk)}>
              <span /><em>{number(index + 1)}</em>
            </button>;
          })}
        </div>
        <div className="lf-progress-value"><strong>{Math.round(progress / total * 100)}<small>%</small></strong><span>阅读位置</span></div>
      </aside>

      <main className="lf-reading-area" aria-label="沉浸式阅读">
        <div className="lf-scene-heading"><span>{scene.number} <i /> {scene.english}</span><span>{scene.line}</span></div>
        {direction === "folio" && <span className="lf-editorial-mark" aria-hidden="true">The art of<br /><em>paying attention.</em></span>}
        {direction === "nocturne" && <span className="lf-night-label">A LITTLE SPACE FOR A BIG IDEA</span>}
        {direction === "duet" && <div className="lf-spread-labels"><span>THE SOURCE / 原文</span><span>THE CONVERSATION / 理解</span></div>}

        <div className="lf-stream" ref={stream} tabIndex={0} aria-label="已加载阅读内容，滚动回看不会推进 Chunk">
          <div className="lf-stream-inner">
            {chunks.map((chunk) => {
              const isCurrent = chunk.chunkId === current?.chunkId;
              const isHighlighted = reviewing ? chunk.chunkId === reviewing : isCurrent;
              const depth = Math.min((current?.index ?? total + 1) - chunk.index, 3);
              const response = reading?.conversation.find((message) => message.chunkId === chunk.chunkId && message.messageId.startsWith("reading-"))?.content ?? chunk.sourceMarkdown;
              return <article key={chunk.chunkId} className="lf-chunk" data-chunk-id={chunk.chunkId} data-current={isCurrent} data-highlight={isHighlighted} data-depth={depth}>
                {direction === "current" && <div className="lf-thread-stamp"><Emblem small /><span>FOCUS<br /><small>CHUNK {number(chunk.index)}</small></span></div>}
                <div className="lf-chunk-body">
                  <div className="lf-chunk-topline"><span className="lf-chunk-index">{direction === "folio" ? "§" : "CHUNK"} {number(chunk.index)} <i>/</i> {number(total)}</span><span className="lf-chunk-state">{isCurrent ? <><i />正在阅读</> : "已读 · 随时回看"}</span></div>
                  <div className="lf-chunk-layout">
                    {direction === "duet" && <div className="lf-source-page"><span className="lf-source-quote">“</span><p>{chunk.sourceMarkdown}</p><span className="lf-source-lines">原文 L{chunk.sourceLines[0]}—{chunk.sourceLines[1]}</span></div>}
                    <div className="lf-response-page">
                      <h1>{chunk.sectionPath.at(-1)}</h1>
                      {direction === "current" && <div className="lf-inline-source"><span>原文</span>{chunk.sourceMarkdown}</div>}
                      {direction === "duet" && <div className="lf-ai-byline"><Emblem small /><span>FOCUS 的讲解</span></div>}
                      <div className="lf-prose">{response.split("\n\n").map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
                      <div className="lf-chunk-footer"><span><Icon name="sparkle" size={13} /> AI 会话投影 <i>·</i> 演示内容</span>
                        <button aria-label={`查看第 ${chunk.index} 段原文`} onClick={() => { setReviewing(isCurrent ? null : chunk.chunkId); showModal("source"); }}><Icon name="book" size={14} />原文<Icon name="chevron" size={11} /></button>
                      </div>
                    </div>
                  </div>
                </div>
                {isHighlighted && direction === "mist" && <span className="lf-card-spark" aria-hidden="true"><Icon name="sparkle" size={21} /></span>}
              </article>;
            })}
            {reading?.status === "completed" && <div className="lf-completed"><Emblem /><span>END OF THIS READING</span><h1>让想法，再停留一会儿。</h1><p>8 个 Chunk 已读完。你可以沿左侧轨迹回看，<br />或按 R 重新体验。阅读进度不代表理解程度。</p></div>}
          </div>
        </div>

        <div className="lf-reading-bottom">
          <div className="lf-position-label">{reviewing ? <button onClick={() => { setReviewing(null); centerChunk(current?.chunkId); }}><Icon name="return" size={14} />回到当前 Chunk {number(current?.index ?? total)}</button> : <span><i />{reading?.status === "completed" ? "本次阅读已完成" : "此刻，只需专注这一段"}</span>}</div>
          <div className="lf-reading-hint"><span>滚动回看</span><i /> <kbd>Space</kbd><span>继续一段</span></div>
          <button className="lf-save" aria-label="标记当前阅读段落" aria-pressed={displayChunk ? bookmarks.includes(displayChunk.chunkId) : false} onClick={toggleBookmark}><Icon name={displayChunk && bookmarks.includes(displayChunk.chunkId) ? "check" : "bookmark"} size={16} /></button>
        </div>
      </main>

      <aside className="lf-companion" aria-label="AI 阅读对话">
        <div className="lf-chat-panel">
          <div className="lf-chat-header"><div className="lf-companion-identity"><Emblem small /><div><h2>{direction === "folio" ? "页边对话" : direction === "duet" ? "一起想一想" : "阅读伙伴"}</h2><span>跟随你的思路，而非催促</span></div></div><span className="lf-status-dot" title="本地演示" /><button className="lf-chat-close lf-icon-button" aria-label="收起对话" onClick={() => setMobileChat(false)}><Icon name="close" /></button></div>
          <div className="lf-chat-context"><Icon name="book" size={13} /><span>围绕 Chunk {number(active?.index ?? 4)} 展开</span><span>演示会话</span></div>
          <div className="lf-chat-messages" ref={chat} role="log" aria-label="当前 Chunk 对话" aria-live="polite">
            <div className="lf-chat-date"><span />此刻的思考<span /></div>
            {conversation.length === 0 && <div className="lf-chat-welcome"><Icon name="sparkle" size={26} /><h3>新的一段，新的思考。</h3><p>「{active?.sectionPath.at(-1)}」<br />哪里让你想再多问一句？</p></div>}
            {conversation.map((message) => <div key={message.messageId} className={`lf-message lf-message-${message.role}`}>
              <span className="lf-message-author">{message.role === "user" ? "你" : <><Emblem small />FOCUS</>}</span>
              <p>{message.content}</p>
              {message.role === "assistant" && <button className="lf-copy" aria-label="复制这条回答" onClick={async () => { try { await navigator.clipboard.writeText(message.content); toast("已复制这条回答"); } catch { toast("浏览器未允许复制，请直接选择文字复制"); } }}><Icon name="copy" size={13} /></button>}
            </div>)}
          </div>
          <div className="lf-chat-bottom">
            <div className="lf-suggestions">
              <span>换个角度想一想</span>
              {["用一句话概括核心", "给我一个具体例子", "和前面的内容有什么联系？"].map((question, index) => <button key={question} disabled={busy || !current} onClick={() => void ask(question)}><Icon name={index === 0 ? "sparkle" : index === 1 ? "book" : "chat"} size={14} /><span>{question}</span><Icon name="chevron" size={12} /></button>)}
            </div>
            <form onSubmit={submit} className="lf-composer"><label className="lf-sr-only" htmlFor="lf-question">关于当前 Chunk 的问题</label><textarea id="lf-question" ref={input} placeholder={current ? "关于这一段，你在想什么？" : "本次阅读已完成，可回看原文"} value={draft} disabled={!current} rows={2} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(); } }} /><div><span>追问，不会推进阅读</span><button aria-label="发送追问" type="submit" disabled={!draft.trim() || busy || !current}><Icon name="up" size={17} /></button></div></form>
            <p className="lf-model-disclaimer">预设回复演示 · 未连接真实 AI</p>
          </div>
        </div>
        <button className="lf-continue" disabled={busy || !current} onClick={() => void advance()}><span><strong>{busy ? "正在加载…" : current ? "继续阅读" : "已到达本篇末尾"}</strong><small>{current ? `只前进一个 Chunk · ${number(current.index)} → ${current.index === total ? "完成" : number(current.index + 1)}` : "给思考一点余地"}</small></span><span className="lf-continue-arrow"><Icon name={current ? "arrow" : "check"} size={21} /></span></button>
      </aside>
    </div>

    <footer className="lf-footer">
      <div className="lf-ambience-controls">
        <details className="lf-settings"><summary aria-label="调整阅读氛围"><Icon name="tune" size={15} /><span>阅读氛围</span></summary><div className="lf-settings-panel"><div className="lf-settings-title"><Icon name="sun" />把光调到刚刚好</div><label htmlFor="light-strength">光场强度 <span>{intensity}%</span></label><input id="light-strength" type="range" min="0" max="100" value={intensity} onInput={(event) => setIntensity(Number(event.currentTarget.value))} onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); adjustLight(event); }} onPointerMove={(event) => { if (event.buttons === 1 && event.currentTarget.hasPointerCapture(event.pointerId)) adjustLight(event); }} onKeyDown={(event) => { const values: Record<string, number> = { ArrowLeft: intensity - 1, ArrowDown: intensity - 1, ArrowRight: intensity + 1, ArrowUp: intensity + 1, Home: 0, End: 100 }; if (event.key in values) { event.preventDefault(); setIntensity(Math.max(0, Math.min(100, values[event.key]))); } }} /><label className="lf-toggle-row">微光粒子<input type="checkbox" checked={particles} onChange={(event) => setParticles(event.target.checked)} /><span /></label><label className="lf-toggle-row">大字阅读<input type="checkbox" checked={largeText} onChange={(event) => { setLargeText(event.target.checked); requestAnimationFrame(() => centerChunk(current?.chunkId, false)); }} /><span /></label><p>跟随系统的减少动态效果设置</p></div></details>
        <span className="lf-light-meter"><Icon name="sun" size={13} />{intensity}%</span>
      </div>
      <span className="lf-footer-state">{scene.label} <i /> CHUNK {number(active?.index ?? 4)} / {number(total)} <i /> 仅本地演示</span>
      <div className="lf-mobile-actions"><button aria-label="展开阅读对话" onClick={() => setMobileChat(!mobileChat)}><Icon name="chat" size={18} /></button><button disabled={!current || busy} onClick={() => void advance()}>继续<Icon name="arrow" size={16} /></button></div>
      {focus && <button className="lf-focus-continue" disabled={!current || busy} onClick={() => void advance()}>继续阅读<Icon name="arrow" size={16} /></button>}
    </footer>
    <div className="lf-toast" role="status" data-visible={Boolean(notice)}><Icon name="check" size={15} />{notice}</div>
    {error && <div className="lf-error" role="alert">{error}</div>}

    <dialog ref={dialog} className={`lf-dialog lf-dialog-${direction}`} onCancel={() => setModal(null)} onClose={() => { setModal(null); lastTrigger.current?.focus(); }} onClick={(event) => { if (event.target === dialog.current) setModal(null); }}>
      <div className="lf-dialog-inner"><button className="lf-icon-button lf-dialog-close" aria-label="关闭" onClick={() => setModal(null)}><Icon name="close" /></button>
        {modal === "source" && displayChunk ? <><span className="lf-dialog-eyebrow">SOURCE ANCHOR · 原文锚点</span><h2>{displayChunk.sectionPath.at(-1)}</h2><p className="lf-dialog-source">{displayChunk.sourceMarkdown}</p><div className="lf-dialog-foot">安静系统 · 第 {displayChunk.index} 段 · L{displayChunk.sourceLines[0]}—{displayChunk.sourceLines[1]}<br />原型合成来源，不是私人 Workspace 数据</div></> : <><span className="lf-dialog-eyebrow">READING PLAN · 阅读目录</span><h2>安静系统</h2><p className="lf-dialog-subtitle">为持续注意力而设计</p><div className="lf-contents">{Array.from({ length: total }, (_, index) => <button key={index} disabled={!chunks[index]} onClick={() => chunks[index] && review(chunks[index])}><span>{number(index + 1)}</span><span>{chunks[index]?.sectionPath.at(-1) ?? "等待下一次继续阅读"}</span>{index < progress ? <Icon name="check" size={15} /> : index + 1 === current?.index ? <span className="lf-contents-here">当前</span> : <span>未读</span>}</button>)}</div><div className="lf-dialog-foot">点击已读段落可回看，不改变 Reading Cursor。</div></>}
      </div>
    </dialog>
  </div>;
}
