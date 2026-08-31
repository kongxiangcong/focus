import type { ReaderChunk, ReaderMessage } from "@focus/reader-contracts";
import type { Ref } from "react";
import { ReaderIcon, ReaderMark } from "./ReaderChrome";

interface ReadingChunkProps {
  chunk: ReaderChunk;
  depth: number;
  entering?: boolean;
  headingRef?: Ref<HTMLHeadingElement>;
  isCurrent?: boolean;
  settling?: boolean;
  reviewing?: boolean;
  onInspect: (chunk: ReaderChunk) => void;
}

export function ReadingChunk({
  chunk,
  depth,
  entering = false,
  headingRef,
  isCurrent = false,
  settling = false,
  reviewing = false,
  onInspect,
}: ReadingChunkProps) {
  return (
    <article
      className="focus-reader__chunk"
      data-chunk-id={chunk.chunkId}
      data-depth={Math.min(depth, 3)}
      data-current={isCurrent}
      data-reviewing={reviewing}
      data-entering={entering || undefined}
      data-settling={settling || undefined}
    >
      <div className="focus-reader__chunk-body">
        <div className="focus-reader__chunk-meta">
          <span>
            CHUNK {String(chunk.index).padStart(2, "0")} <i>/</i>{" "}
            {String(chunk.total).padStart(2, "0")}
          </span>
          <span>
            {isCurrent ? (
              <>
                <i className="focus-reader__dot" />
                正在阅读
              </>
            ) : (
              "已读 · 随时回看"
            )}
          </span>
        </div>
        <h2
          className="focus-reader__eyebrow"
          aria-label={chunk.sectionPath.join(" / ")}
          ref={headingRef}
          tabIndex={isCurrent ? -1 : undefined}
        >
          {chunk.sectionPath.at(-1)}
        </h2>
        <div className="focus-reader__prose">{chunk.sourceMarkdown}</div>
        {chunk.translation !== null ? (
          <section aria-label="译文" className="focus-reader__translation">
            {chunk.translation}
          </section>
        ) : null}
        <footer className="focus-reader__chunk-footer">
          <span>
            <ReaderIcon name="book" size={13} />
            来源原文 <i>·</i> L{chunk.sourceLines.join("—")}
          </span>
          <button
            type="button"
            aria-label={`查看第 ${chunk.index} 段原文`}
            onClick={() => onInspect(chunk)}
          >
            原文锚点
            <ReaderIcon name="chevron" size={12} />
          </button>
        </footer>
      </div>
      {isCurrent && (
        <span className="focus-reader__card-spark" aria-hidden="true">
          <ReaderIcon name="sparkle" size={20} />
        </span>
      )}
    </article>
  );
}

export function ReaderConversation({
  messages,
}: {
  messages: readonly ReaderMessage[];
}) {
  if (messages.length === 0) {
    return (
      <div className="focus-reader__empty">
        <ReaderIcon name="sparkle" size={29} />
        <h3>把你的疑问，留在这里。</h3>
        <p>
          一个例子，一次追问，
          <br />
          让眼前的想法慢慢展开。
        </p>
      </div>
    );
  }

  return (
    <ol aria-label="当前段落对话" className="focus-reader__conversation">
      {messages.map((message) => (
        <li key={message.messageId} data-role={message.role}>
          <span>
            {message.role === "user" ? (
              "你"
            ) : (
              <>
                <ReaderMark />
                FOCUS
              </>
            )}
          </span>
          <p>{message.content}</p>
        </li>
      ))}
    </ol>
  );
}
