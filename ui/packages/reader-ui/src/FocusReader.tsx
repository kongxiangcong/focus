import {
  cursorReceipt,
  type ReaderChunk,
  type ReaderAttachment,
  type ReaderApprovalResponse,
  type ReaderHost,
  type ReadingWindow,
} from "@focus/reader-contracts";
import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useId,
} from "react";

import { AgentControls } from "./AgentControls";
import { ReaderConversation, ReadingChunk } from "./ReadingChunk";
import { projectReaderFrame, type ReaderTransitionFrame } from "./reader-frame";
import {
  ReaderAppearance,
  ReaderDialog,
  ReaderIcon,
  ReaderMark,
  ReaderParticles,
  ReaderProgress,
  type ReaderDialogState,
} from "./ReaderChrome";
import "./reader-shell.css";

const CONTINUE_TRANSITION_MS = 280;

type ReaderPhase = "loading" | "ready" | "continuing" | "sending" | "error";

export interface FocusReaderProps {
  host: ReaderHost;
}

function prefersReducedMotion() {
  return (
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
  );
}

export function FocusReader({ host }: FocusReaderProps) {
  const [settledWindow, setSettledWindow] = useState<ReadingWindow | null>(
    null,
  );
  const [transition, setTransition] = useState<ReaderTransitionFrame | null>(
    null,
  );
  const [phase, setPhase] = useState<ReaderPhase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [attachments, setAttachments] = useState<ReaderAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const revisionRef = useRef(-1);
  function acceptWindow(value: ReadingWindow) {
    if (value.revision !== undefined && value.revision < revisionRef.current) return;
    revisionRef.current = value.revision ?? revisionRef.current;
    setSettledWindow(value);
  }
  const [intensity, setIntensity] = useState(65);
  const [particles, setParticles] = useState(false);
  const [largeText, setLargeText] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [mobileChat, setMobileChat] = useState(false);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [dialogState, setDialogState] = useState<ReaderDialogState | null>(
    null,
  );
  const appRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const chatTriggerRef = useRef<HTMLButtonElement>(null);
  const firstLandingRef = useRef(true);
  const messageId = useId();
  const currentHeadingRef = useRef<HTMLHeadingElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const operationRef = useRef<AbortController | null>(null);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const frameRef = useRef<number | null>(null);

  function beginOperation() {
    if (operationRef.current !== null) {
      return null;
    }
    const controller = new AbortController();
    operationRef.current = controller;
    return controller;
  }

  function finishOperation(controller: AbortController) {
    if (operationRef.current === controller) {
      operationRef.current = null;
    }
  }

  async function loadReadingWindow(
    controller: AbortController,
    resetView: boolean,
  ) {
    if (resetView) {
      setSettledWindow(null);
      setTransition(null);
    }
    setError(null);
    setPhase("loading");
    const result = await host.getReadingWindow(controller.signal);
    if (controller.signal.aborted) {
      return;
    }
    finishOperation(controller);
    if (result.ok) {
      acceptWindow(result.value);
      setTransition(null);
      setError(null);
      setPhase("ready");
      return;
    }
    setError(result.error.message);
    setPhase("error");
  }

  async function reload() {
    const controller = beginOperation();
    if (controller !== null) {
      await loadReadingWindow(controller, false);
    }
  }

  useEffect(() => {
    operationRef.current?.abort();
    revisionRef.current = -1;
    firstLandingRef.current = true;
    setReviewing(null);
    setDialogState(null);
    setMessage("");
    if (settleTimerRef.current !== null) {
      clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    const controller = new AbortController();
    operationRef.current = controller;
    void loadReadingWindow(controller, true);

    return () => {
      controller.abort();
      if (operationRef.current === controller) {
        operationRef.current = null;
      }
    };
  }, [host]);

  useEffect(
    () => () => {
      operationRef.current?.abort();
      if (settleTimerRef.current !== null) {
        clearTimeout(settleTimerRef.current);
      }
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    return host.subscribe?.((result) => {
      if (result.ok) {
        acceptWindow(result.value);
        setTransition(null);
        setError(null);
        setPhase("ready");
      } else { setError(result.error.message); }
    });
  }, [host]);

  async function answerApproval(input: ReaderApprovalResponse) {
    const result = await host.approve?.(input);
    if (result && !result.ok) setError(result.error.message);
  }

  async function stopAgent() {
    const result = await host.stop?.();
    if (result?.ok) acceptWindow(result.value);
    else if (result) setError(result.error.message);
  }

  async function uploadFile(file?: File) {
    if (!file || !host.upload) return;
    setUploading(true);
    const result = await host.upload(file);
    setUploading(false);
    if (result.ok) setAttachments(previous => [...previous, result.value]);
    else setError(result.error.message);
  }

  const readerFrame =
    settledWindow === null
      ? null
      : projectReaderFrame(settledWindow, transition);
  const current = readerFrame?.current ?? null;
  const agent = readerFrame?.window.agent;
  const agentBusy = !!agent?.run && ["running", "approval", "stopping"].includes(agent.run.status);

  function centerChunk(
    chunkId: string | null = current?.chunkId ?? null,
    smooth = true,
  ) {
    const pane = streamRef.current;
    const element = chunkId
      ? Array.from(
          pane?.querySelectorAll<HTMLElement>("[data-chunk-id]") ?? [],
        ).find((node) => node.dataset.chunkId === chunkId)
      : pane?.querySelector<HTMLElement>(".focus-reader__complete");
    if (!pane || !element) return;
    pane.scrollTo?.({
      top:
        element.offsetTop -
        Math.max(24, (pane.clientHeight - element.offsetHeight) / 2),
      behavior: smooth && !prefersReducedMotion() ? "smooth" : "instant",
    });
  }

  function review(chunk: ReaderChunk) {
    setReviewing(chunk.chunkId === current?.chunkId ? null : chunk.chunkId);
    centerChunk(chunk.chunkId);
  }

  useLayoutEffect(() => {
    if (!readerFrame) return;
    const frame = requestAnimationFrame(() => {
      centerChunk(current?.chunkId, !firstLandingRef.current);
      firstLandingRef.current = false;
    });
    return () => cancelAnimationFrame(frame);
  }, [current?.chunkId, readerFrame?.window.status]);

  useLayoutEffect(() => {
    const pane = streamRef.current;
    if (!pane || !appRef.current) return;
    let glowFrame = 0;
    function placeGlow() {
      const article = currentHeadingRef.current?.closest<HTMLElement>(
        ".focus-reader__chunk",
      );
      const app = appRef.current;
      if (!article || !app || !glowRef.current || !pane) return;
      const rect = article.getBoundingClientRect();
      const bounds = app.getBoundingClientRect();
      const viewport = pane.getBoundingClientRect();
      const x = rect.left + rect.width / 2 - bounds.left;
      const y =
        Math.max(
          viewport.top,
          Math.min(rect.top + rect.height / 2, viewport.bottom),
        ) - bounds.top;
      glowRef.current.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
    }
    const onScroll = () => {
      cancelAnimationFrame(glowFrame);
      glowFrame = requestAnimationFrame(placeGlow);
    };
    const onResize = () => {
      centerChunk(reviewing ?? current?.chunkId, false);
      placeGlow();
    };
    const article = currentHeadingRef.current?.closest<HTMLElement>(
      ".focus-reader__chunk",
    );
    const measure = () =>
      `${pane.clientWidth}:${pane.clientHeight}:${article?.offsetWidth}:${article?.offsetHeight}`;
    let size = measure();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            const nextSize = measure();
            // The observer's first delivery must not cancel a Continue or review scroll.
            if (nextSize !== size) {
              size = nextSize;
              onResize();
            }
          });
    observer?.observe(pane);
    if (article) observer?.observe(article);
    placeGlow();
    pane.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(glowFrame);
      observer?.disconnect();
      pane.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, [
    current?.chunkId,
    largeText,
    focusMode,
    reviewing,
    readerFrame?.window.status,
  ]);

  useLayoutEffect(() => {
    centerChunk(reviewing ?? current?.chunkId ?? null, false);
  }, [largeText, focusMode]);

  useLayoutEffect(() => {
    const element = chatRef.current;
    if (element)
      element.scrollTo?.({
        top: element.scrollHeight,
        behavior: prefersReducedMotion() ? "instant" : "smooth",
      });
  }, [readerFrame?.window.conversation, mobileChat]);

  async function continueReading() {
    if (settledWindow === null || phase !== "ready" || agentBusy || uploading) {
      return;
    }
    const receipt = cursorReceipt(settledWindow);
    if (receipt === null) {
      return;
    }
    const controller = beginOperation();
    if (controller === null) {
      return;
    }

    setPhase("continuing");
    const result = await host.continueReading({ receipt }, controller.signal);
    if (controller.signal.aborted) {
      return;
    }
    if (!result.ok) {
      finishOperation(controller);
      if (result.error.code === "cursor-changed") {
        await reload();
        return;
      }
      setError(result.error.message);
      setPhase("error");
      return;
    }

    setError(null);
    setReviewing(null);
    setDialogState(null);
    setMobileChat(false);
    if (prefersReducedMotion()) {
      acceptWindow(result.value);
      setTransition(null);
      setPhase("ready");
      finishOperation(controller);
      frameRef.current = requestAnimationFrame(() => {
        centerChunk(result.value.current?.chunkId ?? null, false);
        currentHeadingRef.current?.focus({ preventScroll: true });
      });
      return;
    }

    setTransition({ target: result.value, active: false });
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = requestAnimationFrame(() => {
        setTransition({ target: result.value, active: true });
      });
    });

    settleTimerRef.current = setTimeout(() => {
      acceptWindow(result.value);
      setTransition(null);
      setPhase("ready");
      finishOperation(controller);
      currentHeadingRef.current?.focus({ preventScroll: true });
    }, CONTINUE_TRANSITION_MS);
  }

  async function sendQuestion(value: string, clearDraft = false) {
    const content = value.trim();
    if (settledWindow === null || phase !== "ready" || agentBusy || uploading || content.length === 0) {
      return;
    }
    const receipt = cursorReceipt(settledWindow);
    if (receipt === null && !host.subscribe) {
      return;
    }
    const controller = beginOperation();
    if (controller === null) {
      return;
    }

    setPhase("sending");
    const result = await host.sendMessage(
      { receipt, content, ...(attachments.length ? { attachmentIds: attachments.map(a => a.attachmentId) } : {}) },
      controller.signal,
    );
    if (controller.signal.aborted) {
      return;
    }
    finishOperation(controller);
    if (result.ok) {
      acceptWindow(result.value);
      setTransition(null);
      if (clearDraft) { setMessage(""); setAttachments([]); }
      setError(null);
      setPhase("ready");
      return;
    }
    if (result.error.code === "cursor-changed") {
      await reload();
      return;
    }
    setError(result.error.message);
    setPhase("error");
  }

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendQuestion(message, true);
  }

  function closeMobileChat() {
    setMobileChat(false);
    chatTriggerRef.current?.focus({ preventScroll: true });
  }

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target !== document.body && !appRef.current?.contains(target)) return;
      if (event.key === "Escape" && mobileChat) {
        closeMobileChat();
        return;
      }
      if (
        event.repeat ||
        event.isComposing ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        dialogState ||
        mobileChat
      )
        return;
      if (
        /^(INPUT|TEXTAREA|SELECT|BUTTON|SUMMARY|A)$/.test(target.tagName) ||
        target.isContentEditable
      )
        return;
      if (event.code === "Space") {
        event.preventDefault();
        void continueReading();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [settledWindow, phase, mobileChat, dialogState]);

  if (readerFrame === null) {
    return (
      <div
        ref={appRef}
        aria-busy={phase === "loading"}
        className="focus-reader"
        data-theme="mist"
        data-phase={phase}
      >
        <div className="focus-reader__initial">
          <ReaderMark />
          <h1>留一点时间，给思考。</h1>
          <p role={error === null ? "status" : "alert"}>
            {error ?? "正在加载阅读内容…"}
          </p>
          {phase === "error" && (
            <button
              className="focus-reader__retry"
              onClick={() => void reload()}
            >
              重试
            </button>
          )}
        </div>
      </div>
    );
  }

  const busy =
    phase === "loading" || phase === "continuing" || phase === "sending";
  const controlsDisabled = agentBusy || uploading || busy || phase === "error";
  const streamChunks = current
    ? [...readerFrame.history, current]
    : readerFrame.history;
  const conversationChunk = current ?? readerFrame.history.at(-1);
  const conversation = agent ? readerFrame.window.conversation : readerFrame.window.conversation.filter(
    (item) => item.chunkId === conversationChunk?.chunkId,
  );
  const total = conversationChunk?.total ?? 0;

  return (
    <div
      ref={appRef}
      className="focus-reader"
      data-theme="mist"
      data-phase={phase}
      data-large-text={largeText}
      data-focus-mode={focusMode}
      data-chat-open={mobileChat}
      aria-busy={busy}
    >
      <div
        className="focus-reader__atmosphere"
        aria-hidden="true"
        style={{ opacity: intensity / 100 }}
      >
        <div className="focus-reader__glow" ref={glowRef} />
        <div className="focus-reader__cool-glow" />
        <div className="focus-reader__violet-glow" />
      </div>
      <div className="focus-reader__grain" aria-hidden="true" />
      {particles && <ReaderParticles />}

      <header className="focus-reader__header">
        <button
          className="focus-reader__brand"
          aria-label="FOCUS 回到当前阅读位置"
          onClick={() => {
            setReviewing(null);
            centerChunk();
          }}
        >
          <ReaderMark />
          <span>
            focus<span>.</span>
          </span>
          <i />
          <small>留一点时间，给思考</small>
        </button>
        <h1
          className="focus-reader__source-title"
          title={readerFrame.window.source.title}
        >
          {readerFrame.window.source.title}
        </h1>
        <div className="focus-reader__header-actions">
          <span className="focus-reader__private">
            <ReaderIcon name="book" size={13} />
            私人阅读空间
          </span>
          <button
            className="focus-reader__icon-button"
            aria-label="阅读目录"
            title="阅读目录"
            onClick={() => setDialogState({ kind: "contents" })}
          >
            <ReaderIcon name="list" />
          </button>
          <button
            className="focus-reader__icon-button"
            aria-label={focusMode ? "退出专注模式" : "专注模式"}
            title="专注模式"
            aria-pressed={focusMode}
            onClick={() => setFocusMode(!focusMode)}
          >
            <ReaderIcon name="focus" />
          </button>
        </div>
      </header>

      {error !== null && (
        <div className="focus-reader__error" role="alert">
          {error}
          <button onClick={() => void reload()}>重试</button>
        </div>
      )}

      <div className="focus-reader__workspace">
        <ReaderProgress
          chunks={streamChunks}
          current={current}
          onReview={review}
        />
        <main className="focus-reader__reading" aria-label="沉浸式阅读">
          <div className="focus-reader__reading-header">
            <span>
              MIST <i /> 雾光
            </span>
            <span>让注意力，轻轻落在此刻。</span>
          </div>
          <div
            className="focus-reader__stream"
            role="region"
            aria-label="连续阅读内容"
            tabIndex={0}
            ref={streamRef}
          >
            <div className="focus-reader__stream-inner">
              {streamChunks.map((chunk, index) => {
                const isCurrent = chunk.chunkId === current?.chunkId;
                const depth = isCurrent
                  ? 0
                  : readerFrame.history.length - index;
                return (
                  <ReadingChunk
                    key={chunk.chunkId}
                    chunk={chunk}
                    depth={depth}
                    entering={isCurrent && readerFrame.enteringCurrent}
                    isCurrent={isCurrent}
                    headingRef={isCurrent ? currentHeadingRef : undefined}
                    reviewing={chunk.chunkId === reviewing}
                    settling={chunk.chunkId === readerFrame.settlingChunkId}
                    onInspect={(selected) =>
                      setDialogState({ kind: "source", chunk: selected })
                    }
                  />
                );
              })}
              {current === null && (
                <section className="focus-reader__complete">
                  <ReaderMark />
                  <span>END OF THIS READING</span>
                  <h2 ref={currentHeadingRef} tabIndex={-1}>
                    {readerFrame.window.status === "empty" ? "从一篇论文开始" : "阅读完成"}
                  </h2>
                  <p>
                    {readerFrame.window.status === "empty" ? "在对话框输入阅读需求，选择 PDF / HTML，或选择已有来源。" : "可以回看原文、继续提问，或开始阅读另一份来源。"}
                  </p>
                </section>
              )}
            </div>
          </div>
          <div className="focus-reader__reading-bottom">
            {reviewing ? (
              <button
                onClick={() => {
                  setReviewing(null);
                  centerChunk();
                }}
              >
                <ReaderIcon name="return" size={14} />
                回到当前阅读位置
              </button>
            ) : (
              <span>
                <i className="focus-reader__dot" />
                {current ? "此刻，只需专注这一段" : "进度是位置，不是理解评价"}
              </span>
            )}
            <span className="focus-reader__keyboard-hint">
              滚动回看
              <i />
              <kbd>Space</kbd>继续一段
            </span>
          </div>
        </main>

        <aside className="focus-reader__companion" aria-label="阅读伙伴">
          <div className="focus-reader__companion-header">
            <ReaderMark />
            <div>
              <h2>阅读伙伴</h2>
              <span>跟随你的思路，而非催促</span>
            </div>
            <i className="focus-reader__dot" />
            <button
              className="focus-reader__icon-button focus-reader__chat-close"
              aria-label="收起对话"
              onClick={closeMobileChat}
            >
              <ReaderIcon name="close" />
            </button>
          </div>
          <div className="focus-reader__conversation-context">
            <ReaderIcon name="book" size={13} />
            {current
              ? `围绕 Chunk ${String(current.index).padStart(2, "0")} 展开`
              : readerFrame.window.status === "empty" ? "开始新的阅读" : "本篇阅读已完成"}
            <span>同一阅读位置</span>
          </div>
          <div
            className="focus-reader__chat-scroll"
            ref={chatRef}
            role="log"
            aria-label="当前 Chunk 对话"
            aria-live="polite"
            aria-relevant="additions text"
          >
            <ReaderConversation messages={conversation} />
          </div>
          <div className="focus-reader__chat-bottom">
            {agent && <AgentControls agent={agent} onStop={() => void stopAgent()} onAnswer={input => void answerApproval(input)} />}
            {agent && <label className="focus-agent__source">已有来源 / Topic
              <select aria-label="选择阅读来源" disabled={controlsDisabled} value="" onChange={e => {
                if (e.target.value) void sendQuestion(`开始阅读 ${e.target.value}`);
              }}><option value="">选择…</option>
                {agent.catalog.sources.map(s => <option key={s.sourceId} value={`Source ${s.sourceId}`}>{s.title}</option>)}
                {agent.catalog.topics.map(t => <option key={t.topicId} value={`Topic ${t.topicId}`}>Topic · {t.title}</option>)}
              </select>
            </label>}
            {host.upload && <label className="focus-agent__upload">{uploading ? "正在上传…" : "选择 PDF / HTML"}
              <input aria-label="选择论文文件" type="file" accept=".pdf,.html" disabled={controlsDisabled} onChange={e => {
                void uploadFile(e.target.files?.[0]); e.target.value = "";
              }} />
            </label>}
            {attachments.map(a => <div key={a.attachmentId}>{a.name} <button disabled={controlsDisabled} onClick={() => setAttachments(old => old.filter(v => v.attachmentId !== a.attachmentId))}>移除</button></div>)}
            <div className="focus-reader__suggestions">
              <span>换个角度想一想</span>
              {[
                "用一句话概括核心",
                "给我一个具体例子",
                "和前面的内容有什么联系？",
              ].map((question, index) => (
                <button
                  type="button"
                  key={question}
                  disabled={controlsDisabled || (!current && !agent)}
                  onClick={() => void sendQuestion(question)}
                >
                  <ReaderIcon
                    name={
                      index === 0 ? "sparkle" : index === 1 ? "book" : "chat"
                    }
                    size={14}
                  />
                  <span>{question}</span>
                  <ReaderIcon name="chevron" size={12} />
                </button>
              ))}
            </div>
            <form className="focus-reader__composer" onSubmit={submitQuestion}>
              <label className="focus-reader__sr-only" htmlFor={messageId}>
                针对当前 Reading Chunk 提问
              </label>
              <textarea
                id={messageId}
                ref={questionRef}
                disabled={controlsDisabled || (!current && !agent)}
                rows={2}
                value={message}
                placeholder={
                  current
                    ? "关于这一段，你在想什么？"
                    : "我要阅读…（可选择 PDF / HTML）"
                }
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    void sendQuestion(message, true);
                  }
                }}
              />
              <div>
                <span>追问，不会推进阅读</span>
                <button
                  type="submit"
                  aria-label={phase === "sending" ? "正在发送…" : "发送"}
                  disabled={controlsDisabled || (!current && !agent) || !message.trim()}
                >
                  <ReaderIcon name="up" size={17} />
                </button>
              </div>
            </form>
            <p className="focus-reader__host-note">对话由当前阅读宿主提供</p>
          </div>
        </aside>
        <div className="focus-reader__action">
          <button
            className="focus-reader__continue"
            type="button"
            aria-label={phase === "continuing" ? "正在继续…" : "继续阅读"}
            aria-busy={phase === "continuing"}
            disabled={controlsDisabled || !current}
            onClick={() => void continueReading()}
          >
            <span>
              <strong>
                {phase === "continuing"
                  ? "正在继续…"
                  : current
                    ? "继续阅读"
                    : readerFrame.window.status === "empty" ? "开始新的阅读" : "本篇阅读已完成"}
              </strong>
              <small>
                {current
                  ? `只前进一个 Chunk · ${String(current.index).padStart(2, "0")} → ${current.index === total ? "完成" : String(current.index + 1).padStart(2, "0")}`
                  : "给思考一点余地"}
              </small>
            </span>
            <i>
              <ReaderIcon name={current ? "arrow" : "check"} size={21} />
            </i>
          </button>
        </div>
      </div>

      <footer className="focus-reader__footer">
        <div className="focus-reader__ambience">
          <ReaderAppearance
            intensity={intensity}
            onIntensity={setIntensity}
            particles={particles}
            onParticles={setParticles}
            largeText={largeText}
            onLargeText={setLargeText}
          />
          <span>
            <ReaderIcon name="sun" size={13} />
            {intensity}%
          </span>
        </div>
        <span className="focus-reader__theme-label">
          雾光
          <i />
          默认阅读主题
        </span>
        <button
          className="focus-reader__mobile-chat"
          ref={chatTriggerRef}
          aria-label="展开阅读对话"
          aria-expanded={mobileChat}
          onClick={() => {
            setMobileChat(!mobileChat);
            if (!mobileChat) {
              setFocusMode(false);
              requestAnimationFrame(() =>
                questionRef.current?.focus({ preventScroll: true }),
              );
            }
          }}
        >
          <ReaderIcon name="chat" />
        </button>
      </footer>
      <ReaderDialog
        state={dialogState}
        chunks={streamChunks}
        current={current}
        sourceTitle={readerFrame.window.source.title}
        onClose={() => setDialogState(null)}
        onReview={review}
      />
    </div>
  );
}
