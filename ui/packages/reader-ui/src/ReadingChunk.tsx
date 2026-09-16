import type { ReaderChunk, ReaderMessage } from "@focus/reader-contracts";
import { useState } from "react";
import { MarkdownContent } from "./MarkdownContent";

export const chunkKey = (c: { sourceId: string; planId: string; chunkId: string }) => `${c.sourceId}/${c.planId}/${c.chunkId}`;

export function ReadingChunk({ chunk, onReference }: { chunk: ReaderChunk; onReference: (chunk: ReaderChunk) => void }) {
  const [original, setOriginal] = useState(false);
  const translated = chunk.translation !== null && !original;
  const text = translated ? chunk.translation! : chunk.sourceMarkdown;
  return <article className="focus-reading" data-chunk-key={chunkKey(chunk)}>
    <header className="focus-reading__meta"><span>{translated ? "译文" : "原文"}</span><span>第 {chunk.index} / {chunk.total} 段</span>
      {chunk.translation !== null && <button aria-pressed={original} onClick={() => setOriginal(!original)}>{original ? "查看译文" : "查看原文"}</button>}
    </header>
    <h2>{chunk.sectionPath.at(-1)}</h2>
    <MarkdownContent text={text} sourceId={chunk.sourceId} />
    {chunk.images.filter(i => !text.includes(i.src) && !text.includes(decodeURIComponent(i.src.split('/').at(-1)!))).map(i =>
      <figure key={i.src}><img src={i.src} alt={i.caption} loading="lazy" /><figcaption>{i.caption}</figcaption></figure>)}
    <footer><button onClick={() => onReference(chunk)}>引用这段提问</button></footer>
  </article>;
}

export function ReaderConversation({ messages }: { messages: readonly ReaderMessage[] }) {
  return <>{messages.map(message => <article className="focus-message" data-role={message.role} key={message.messageId}>
    <header>{message.role === "user" ? "你" : "Codex"}</header>
    <MarkdownContent text={message.content} />
  </article>)}</>;
}
