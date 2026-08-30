import type { ReaderChunk, ReaderMessage } from "@focus/reader-contracts";
import type { ReactNode, Ref } from "react";

interface ReadingChunkProps {
  chunk: ReaderChunk;
  depth: number;
  entering?: boolean;
  headingRef?: Ref<HTMLHeadingElement>;
  isCurrent?: boolean;
  settling?: boolean;
  children?: ReactNode;
}

export function ReadingChunk({
  chunk,
  depth,
  entering = false,
  headingRef,
  isCurrent = false,
  settling = false,
  children,
}: ReadingChunkProps) {
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
        <section aria-label="译文" className="focus-reader__translation">
          {chunk.translation}
        </section>
      ) : null}
      {children}
    </article>
  );
}

export function ReaderConversation({ messages }: { messages: readonly ReaderMessage[] }) {
  if (messages.length === 0) {
    return <p className="focus-reader__empty">这一段还没有旁注。</p>;
  }

  return (
    <ol aria-label="当前段落对话" className="focus-reader__conversation">
      {messages.map((message) => (
        <li key={message.messageId} data-role={message.role}>
          <span>{message.role === "user" ? "你" : "Focus"}</span>
          <p>{message.content}</p>
        </li>
      ))}
    </ol>
  );
}
