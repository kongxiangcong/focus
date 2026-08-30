import {
  cursorReceipt,
  type ReaderChunk,
  type ReaderHost,
  type ReaderMessage,
  type ReadingWindow,
} from "@focus/reader-contracts";
import { FormEvent, useEffect, useState } from "react";

import "./reader-shell.css";

type ReaderPhase = "loading" | "ready" | "continuing" | "sending" | "error";

export interface FocusReaderProps {
  host: ReaderHost;
}

function ChunkContent({ chunk }: { chunk: ReaderChunk }) {
  return (
    <article className="focus-reader__chunk" data-chunk-id={chunk.chunkId}>
      <p className="focus-reader__eyebrow">{chunk.sectionPath.join(" / ")}</p>
      <pre className="focus-reader__source">{chunk.sourceMarkdown}</pre>
      {chunk.translation !== null ? (
        <section aria-label="Translation" className="focus-reader__translation">
          {chunk.translation}
        </section>
      ) : null}
    </article>
  );
}

function Conversation({ messages }: { messages: readonly ReaderMessage[] }) {
  if (messages.length === 0) {
    return <p className="focus-reader__empty">No conversation for this chunk.</p>;
  }

  return (
    <ol aria-label="Conversation" className="focus-reader__conversation">
      {messages.map((message) => (
        <li key={message.messageId} data-role={message.role}>
          <strong>{message.role === "user" ? "You" : "Focus"}</strong>
          <p>{message.content}</p>
        </li>
      ))}
    </ol>
  );
}

export function FocusReader({ host }: FocusReaderProps) {
  const [window, setWindow] = useState<ReadingWindow | null>(null);
  const [phase, setPhase] = useState<ReaderPhase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  async function reload(signal?: AbortSignal) {
    const result = await host.getReadingWindow(signal);
    if (result.ok) {
      setWindow(result.value);
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

  async function continueReading() {
    if (window === null || phase !== "ready") {
      return;
    }
    const receipt = cursorReceipt(window);
    if (receipt === null) {
      return;
    }
    setPhase("continuing");
    const result = await host.continueReading({ receipt });
    if (result.ok) {
      setWindow(result.value);
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

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (window === null || phase !== "ready" || content.length === 0) {
      return;
    }
    const receipt = cursorReceipt(window);
    if (receipt === null) {
      return;
    }
    setPhase("sending");
    const result = await host.sendMessage({ receipt, content });
    if (result.ok) {
      setWindow(result.value);
      setMessage("");
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

  if (window === null) {
    return (
      <main className="focus-reader" data-phase={phase}>
        <p>{error ?? "Loading Focus Reader…"}</p>
        {phase === "error" ? <button onClick={() => void reload()}>Retry</button> : null}
      </main>
    );
  }

  const current = window.current;
  const busy = phase === "continuing" || phase === "sending";

  return (
    <main className="focus-reader" data-phase={phase}>
      <header className="focus-reader__header">
        <div>
          <p className="focus-reader__brand">FOCUS</p>
          <h1>{window.source.title}</h1>
        </div>
        <p aria-label="Reading progress">
          {current === null ? "Complete" : `${current.index} / ${current.total}`}
        </p>
      </header>

      {error !== null ? (
        <div className="focus-reader__error" role="alert">
          {error} <button onClick={() => void reload()}>Retry</button>
        </div>
      ) : null}

      <section aria-label="Reading history" className="focus-reader__history">
        {window.history.map((chunk) => (
          <ChunkContent chunk={chunk} key={chunk.chunkId} />
        ))}
      </section>

      {current === null ? (
        <section className="focus-reader__complete">
          <h2>Reading complete</h2>
          <p>The host reports that no current Reading Chunk remains.</p>
        </section>
      ) : (
        <ChunkContent chunk={current} />
      )}

      <section aria-label="Reader conversation" className="focus-reader__dialogue">
        <Conversation messages={window.conversation} />
        <form onSubmit={(event) => void sendMessage(event)}>
          <label htmlFor="focus-reader-message">Ask about the current chunk</label>
          <textarea
            disabled={busy || current === null}
            id="focus-reader-message"
            onChange={(event) => setMessage(event.target.value)}
            rows={3}
            value={message}
          />
          <button disabled={busy || current === null || message.trim().length === 0} type="submit">
            {phase === "sending" ? "Sending…" : "Send"}
          </button>
        </form>
      </section>

      <footer className="focus-reader__footer">
        <button disabled={busy || current === null} onClick={() => void continueReading()} type="button">
          {phase === "continuing" ? "Continuing…" : "Continue reading"}
        </button>
      </footer>
    </main>
  );
}
