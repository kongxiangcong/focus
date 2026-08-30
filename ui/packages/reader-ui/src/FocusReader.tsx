import {
  cursorReceipt,
  type ReaderChunk,
  type ReaderHost,
  type ReaderMessage,
  type ReadingWindow,
} from "@focus/reader-contracts";
import {
  type CSSProperties,
  type FormEvent,
  type ReactNode,
  type Ref,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import "./reader-shell.css";

type ReaderPhase = "loading" | "ready" | "continuing" | "sending" | "error";

interface ReaderTransition {
  next: ReadingWindow;
  active: boolean;
}

export interface FocusReaderProps {
  host: ReaderHost;
}

interface ChunkContentProps {
  chunk: ReaderChunk;
  depth: number;
  entering?: boolean;
  headingRef?: Ref<HTMLHeadingElement>;
  isCurrent?: boolean;
  settling?: boolean;
  children?: ReactNode;
}

function ChunkContent({
  chunk,
  depth,
  entering = false,
  headingRef,
  isCurrent = false,
  settling = false,
  children,
}: ChunkContentProps) {
  return (
    <article
      className="focus-reader__chunk"
      data-chunk-id={chunk.chunkId}
      data-depth={Math.min(depth, 3)}
      data-entering={entering || undefined}
      data-settling={settling || undefined}
    >
      <h2 className="focus-reader__eyebrow" ref={headingRef} tabIndex={isCurrent ? -1 : undefined}>
        {chunk.sectionPath.join(" / ")}
      </h2>
      <div className="focus-reader__prose">{chunk.sourceMarkdown}</div>
      {chunk.translation !== null ? (
        <section aria-label="Translation" className="focus-reader__translation">
          {chunk.translation}
        </section>
      ) : null}
      {children}
    </article>
  );
}

function Conversation({ messages }: { messages: readonly ReaderMessage[] }) {
  if (messages.length === 0) {
    return <p className="focus-reader__empty">No notes for this passage yet.</p>;
  }

  return (
    <ol aria-label="Conversation" className="focus-reader__conversation">
      {messages.map((message) => (
        <li key={message.messageId} data-role={message.role}>
          <span>{message.role === "user" ? "You" : "Focus"}</span>
          <p>{message.content}</p>
        </li>
      ))}
    </ol>
  );
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function FocusReader({ host }: FocusReaderProps) {
  const [readingWindow, setReadingWindow] = useState<ReadingWindow | null>(null);
  const [transition, setTransition] = useState<ReaderTransition | null>(null);
  const [phase, setPhase] = useState<ReaderPhase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [glowTransform, setGlowTransform] = useState("translate3d(50vw, 55vh, 0) translate(-50%, -50%)");
  const currentHeadingRef = useRef<HTMLHeadingElement>(null);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const frameRef = useRef<number | null>(null);

  async function reload(signal?: AbortSignal) {
    const result = await host.getReadingWindow(signal);
    if (result.ok) {
      setReadingWindow(result.value);
      setTransition(null);
      setError(null);
      setPhase("ready");
      return;
    }
    if (signal?.aborted) {
      return;
    }
    setError(result.error.message);
    setPhase("error");
  }

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [host]);

  useEffect(
    () => () => {
      if (settleTimerRef.current !== null) {
        clearTimeout(settleTimerRef.current);
      }
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
    },
    [],
  );

  const projectedWindow = transition?.next ?? readingWindow;
  const current = projectedWindow?.current ?? null;

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
    if (readingWindow === null || phase !== "ready") {
      return;
    }
    const receipt = cursorReceipt(readingWindow);
    if (receipt === null) {
      return;
    }

    setPhase("continuing");
    const result = await host.continueReading({ receipt });
    if (result.ok) {
      const reduceMotion = prefersReducedMotion();
      setError(null);
      setAnnotationOpen(false);
      if (reduceMotion) {
        setReadingWindow(result.value);
        setTransition(null);
        setPhase("ready");
        frameRef.current = requestAnimationFrame(() => {
          currentHeadingRef.current?.scrollIntoView?.({ behavior: "auto", block: "center" });
          currentHeadingRef.current?.focus({ preventScroll: true });
        });
        return;
      }

      setTransition({ next: result.value, active: false });

      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = requestAnimationFrame(() => {
          setTransition({ next: result.value, active: true });
          currentHeadingRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
        });
      });

      settleTimerRef.current = setTimeout(
        () => {
          setReadingWindow(result.value);
          setTransition(null);
          setPhase("ready");
          currentHeadingRef.current?.focus({ preventScroll: true });
        },
        560,
      );
      return;
    }
    if (result.error.code === "cursor-changed") {
      await reload();
      return;
    }
    setError(result.error.message);
    setPhase("error");
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (readingWindow === null || phase !== "ready" || content.length === 0) {
      return;
    }
    const receipt = cursorReceipt(readingWindow);
    if (receipt === null) {
      return;
    }
    setPhase("sending");
    const result = await host.sendMessage({ receipt, content });
    if (result.ok) {
      setReadingWindow(result.value);
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

  if (readingWindow === null || projectedWindow === null) {
    return (
      <main className="focus-reader" data-phase={phase}>
        <p>{error ?? "Loading Focus Reader…"}</p>
        {phase === "error" ? <button onClick={() => void reload()}>Retry</button> : null}
      </main>
    );
  }

  const busy = phase === "continuing" || phase === "sending";
  const history = transition !== null && readingWindow.current !== null
    ? [...readingWindow.history, readingWindow.current]
    : readingWindow.history;
  const progress = current === null ? 100 : (current.index / current.total) * 100;
  const progressStyle = { "--reader-progress": progress / 100 } as CSSProperties;

  return (
    <main className="focus-reader" data-phase={phase}>
      <div aria-hidden="true" className="focus-reader__glow" style={{ transform: glowTransform }} />

      <header className="focus-reader__header">
        <h1>{projectedWindow.source.title}</h1>
        <div
          aria-label={current === null ? "Reading complete" : `Reading position ${current.index} of ${current.total}`}
          aria-valuemax={current?.total ?? 1}
          aria-valuemin={0}
          aria-valuenow={current?.index ?? 1}
          className="focus-reader__progress"
          role="progressbar"
          style={progressStyle}
        >
          <span />
        </div>
      </header>

      {error !== null ? (
        <div className="focus-reader__error" role="alert">
          {error} <button onClick={() => void reload()}>Retry</button>
        </div>
      ) : null}

      <section aria-label="Reading passage" className="focus-reader__stream">
        {history.map((chunk, index) => {
          const depth = history.length - index;
          return (
            <ChunkContent
              chunk={chunk}
              depth={depth}
              key={chunk.chunkId}
              settling={transition !== null && chunk.chunkId === readingWindow.current?.chunkId}
            />
          );
        })}

        {current === null ? (
          <section className="focus-reader__complete">
            <h2>Reading complete</h2>
            <p>The host reports that no current Reading Chunk remains.</p>
          </section>
        ) : (
          <ChunkContent
            chunk={current}
            depth={0}
            entering={transition !== null && !transition.active}
            headingRef={currentHeadingRef}
            isCurrent
            key={current.chunkId}
          >
            <aside aria-label="Notes for the current passage" className="focus-reader__marginalia">
              <button
                aria-expanded={annotationOpen}
                className="focus-reader__marginalia-toggle"
                disabled={phase === "continuing"}
                onClick={() => setAnnotationOpen((open) => !open)}
                type="button"
              >
                {annotationOpen ? "Close notes" : "Ask about this passage…"}
              </button>
              {annotationOpen ? (
                <div className="focus-reader__marginalia-body">
                  <Conversation messages={projectedWindow.conversation} />
                  <form onSubmit={(event) => void sendMessage(event)}>
                    <label htmlFor="focus-reader-message">Ask about the current chunk</label>
                    <textarea
                      disabled={busy}
                      id="focus-reader-message"
                      onChange={(event) => setMessage(event.target.value)}
                      rows={2}
                      value={message}
                    />
                    <button disabled={busy || message.trim().length === 0} type="submit">
                      {phase === "sending" ? "Sending…" : "Send"}
                    </button>
                  </form>
                </div>
              ) : null}
            </aside>
          </ChunkContent>
        )}
      </section>

      <footer className="focus-reader__footer">
        <button
          aria-busy={phase === "continuing"}
          disabled={busy || current === null}
          onClick={() => void continueReading()}
          type="button"
        >
          {phase === "continuing" ? "Continuing…" : "Continue reading"}
        </button>
      </footer>
    </main>
  );
}
