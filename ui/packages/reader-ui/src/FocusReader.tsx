import {
  cursorReceipt,
  type ReaderHost,
  type ReadingWindow,
} from "@focus/reader-contracts";
import {
  type CSSProperties,
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { ReaderConversation, ReadingChunk } from "./ReadingChunk";
import { projectReaderFrame, type ReaderTransitionFrame } from "./reader-frame";
import "./reader-shell.css";

const CONTINUE_TRANSITION_MS = 280;

type ReaderPhase = "loading" | "ready" | "continuing" | "sending" | "error";

export interface FocusReaderProps {
  host: ReaderHost;
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function FocusReader({ host }: FocusReaderProps) {
  const [settledWindow, setSettledWindow] = useState<ReadingWindow | null>(null);
  const [transition, setTransition] = useState<ReaderTransitionFrame | null>(null);
  const [phase, setPhase] = useState<ReaderPhase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [glowTransform, setGlowTransform] = useState("translate3d(50vw, 55vh, 0) translate(-50%, -50%)");
  const currentHeadingRef = useRef<HTMLHeadingElement>(null);
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

  async function reload() {
    const controller = beginOperation();
    if (controller === null) {
      return;
    }
    setError(null);
    setPhase("loading");
    const result = await host.getReadingWindow(controller.signal);
    if (controller.signal.aborted) {
      return;
    }
    finishOperation(controller);
    if (result.ok) {
      setSettledWindow(result.value);
      setTransition(null);
      setError(null);
      setPhase("ready");
      return;
    }
    setError(result.error.message);
    setPhase("error");
  }

  useEffect(() => {
    operationRef.current?.abort();
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
    setSettledWindow(null);
    setTransition(null);
    setError(null);
    setPhase("loading");

    void host.getReadingWindow(controller.signal).then((result) => {
      if (controller.signal.aborted) {
        return;
      }
      finishOperation(controller);
      if (result.ok) {
        setSettledWindow(result.value);
        setPhase("ready");
        return;
      }
      setError(result.error.message);
      setPhase("error");
    });

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

  const readerFrame = settledWindow === null ? null : projectReaderFrame(settledWindow, transition);
  const current = readerFrame?.current ?? null;

  useLayoutEffect(() => {
    if (current === null || currentHeadingRef.current === null) {
      return;
    }

    const placeGlow = () => {
      const article = currentHeadingRef.current?.closest<HTMLElement>(".focus-reader__chunk");
      if (article === null || article === undefined) {
        return;
      }
      const rect = article.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = Math.min(rect.top + rect.height / 2, globalThis.innerHeight * 0.58);
      setGlowTransform(`translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`);
    };

    placeGlow();
    globalThis.addEventListener("resize", placeGlow);
    return () => globalThis.removeEventListener("resize", placeGlow);
  }, [current?.chunkId]);

  async function continueReading() {
    if (settledWindow === null || phase !== "ready") {
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
    setAnnotationOpen(false);
    if (prefersReducedMotion()) {
      setSettledWindow(result.value);
      setTransition(null);
      setPhase("ready");
      finishOperation(controller);
      frameRef.current = requestAnimationFrame(() => {
        currentHeadingRef.current?.scrollIntoView?.({ behavior: "auto", block: "center" });
        currentHeadingRef.current?.focus({ preventScroll: true });
      });
      return;
    }

    setTransition({ target: result.value, active: false });
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = requestAnimationFrame(() => {
        setTransition({ target: result.value, active: true });
        currentHeadingRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      });
    });

    settleTimerRef.current = setTimeout(() => {
      setSettledWindow(result.value);
      setTransition(null);
      setPhase("ready");
      finishOperation(controller);
      currentHeadingRef.current?.focus({ preventScroll: true });
    }, CONTINUE_TRANSITION_MS);
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (settledWindow === null || phase !== "ready" || content.length === 0) {
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

    setPhase("sending");
    const result = await host.sendMessage({ receipt, content }, controller.signal);
    if (controller.signal.aborted) {
      return;
    }
    finishOperation(controller);
    if (result.ok) {
      setSettledWindow(result.value);
      setTransition(null);
      setMessage("");
      setAnnotationOpen(true);
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

  if (readerFrame === null) {
    return (
      <main aria-busy={phase === "loading"} className="focus-reader" data-phase={phase}>
        <p className="focus-reader__status" role={error === null ? undefined : "alert"}>
          {error ?? "正在加载阅读内容…"}
        </p>
        {phase === "error" ? <button onClick={() => void reload()}>重试</button> : null}
      </main>
    );
  }

  const busy = phase === "loading" || phase === "continuing" || phase === "sending";
  const progress = current === null ? 100 : (current.index / current.total) * 100;
  const progressMax = current?.total ?? readerFrame.history.at(-1)?.total ?? 1;
  const progressStyle = { "--reader-progress": progress / 100 } as CSSProperties;

  return (
    <main aria-busy={busy} className="focus-reader" data-phase={phase}>
      <div aria-hidden="true" className="focus-reader__glow" style={{ transform: glowTransform }} />

      <header className="focus-reader__header">
        <h1>{readerFrame.window.source.title}</h1>
        <div
          aria-label={current === null ? "阅读完成" : `阅读位置：第 ${current.index} 段，共 ${current.total} 段`}
          aria-valuemax={progressMax}
          aria-valuemin={0}
          aria-valuenow={current?.index ?? progressMax}
          className="focus-reader__progress"
          role="progressbar"
          style={progressStyle}
        >
          <span />
        </div>
      </header>

      {error !== null ? (
        <div className="focus-reader__error" role="alert">
          {error} <button onClick={() => void reload()}>重试</button>
        </div>
      ) : null}

      <section aria-label="连续阅读内容" className="focus-reader__stream">
        {readerFrame.history.map((chunk, index) => {
          const depth = readerFrame.history.length - index;
          return (
            <ReadingChunk
              chunk={chunk}
              depth={depth}
              key={chunk.chunkId}
              settling={chunk.chunkId === readerFrame.settlingChunkId}
            />
          );
        })}

        {current === null ? (
          <section className="focus-reader__complete">
            <h2>阅读完成</h2>
            <p>当前 Reading Plan 已经没有待阅读的 Reading Chunk。</p>
          </section>
        ) : (
          <ReadingChunk
            chunk={current}
            depth={0}
            entering={readerFrame.enteringCurrent}
            headingRef={currentHeadingRef}
            isCurrent
            key={current.chunkId}
          >
            <aside aria-label="当前段落旁注" className="focus-reader__marginalia">
              <button
                aria-expanded={annotationOpen}
                className="focus-reader__marginalia-toggle"
                disabled={phase === "continuing"}
                onClick={() => setAnnotationOpen((open) => !open)}
                type="button"
              >
                {annotationOpen ? "收起旁注" : "针对这一段提问…"}
              </button>
              {annotationOpen ? (
                <div className="focus-reader__marginalia-body">
                  <ReaderConversation messages={readerFrame.window.conversation} />
                  <form onSubmit={(event) => void sendMessage(event)}>
                    <label htmlFor="focus-reader-message">针对当前 Reading Chunk 提问</label>
                    <textarea
                      disabled={busy}
                      id="focus-reader-message"
                      onChange={(event) => setMessage(event.target.value)}
                      rows={2}
                      value={message}
                    />
                    <button disabled={busy || message.trim().length === 0} type="submit">
                      {phase === "sending" ? "正在发送…" : "发送"}
                    </button>
                  </form>
                </div>
              ) : null}
            </aside>
          </ReadingChunk>
        )}
      </section>

      <footer className="focus-reader__footer">
        <button
          aria-busy={phase === "continuing"}
          disabled={busy || current === null}
          onClick={() => void continueReading()}
          type="button"
        >
          {phase === "continuing" ? "正在继续…" : "继续阅读"}
        </button>
      </footer>
    </main>
  );
}
