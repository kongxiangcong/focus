import type { ReaderChunk, ReaderMessage } from "@focus/reader-contracts";
import { useState } from "react";
import { MarkdownContent } from "./MarkdownContent";

export const chunkKey = (c: { sourceId: string; planId: string; chunkId: string }) => `${c.sourceId}/${c.planId}/${c.chunkId}`;

export function ReadingChunk({ chunk, onReference }: { chunk: ReaderChunk; onReference: (chunk: ReaderChunk) => void }) {
  const [original, setOriginal] = useState(false);
  const translated = chunk.translation !== null && !original;
  const preparing = !original && chunk.presentationStatus === "translation-required" && chunk.translation === null;
  const text = preparing ? "" : translated ? chunk.translation! : chunk.sourceMarkdown;
  return <article className="focus-reading focus-reader__chunk" data-chunk-key={chunkKey(chunk)}>
    <header className="focus-reading__meta"><span>{preparing ? "待准备" : translated ? "译文" : "原文"}</span><span>第 {chunk.index} / {chunk.total} 段</span>
      {chunk.translation !== null && <button aria-pressed={original} onClick={() => setOriginal(!original)}>{original ? "查看译文" : "查看原文"}</button>}
    </header>
    <h2>{chunk.sectionPath.at(-1)}</h2>
    {preparing ? <p role="status">译文尚未准备完成，请打开材料继续准备。</p> : <MarkdownContent text={text} sourceId={chunk.sourceId} />}
    {!preparing && chunk.images.filter(i => !text.includes(i.src) && !text.includes(decodeURIComponent(i.src.split('/').at(-1)!))).map(i =>
      <figure key={i.src}><img src={i.src} alt={i.caption} loading="lazy" /><figcaption>{i.caption}</figcaption></figure>)}
    <footer><button onClick={() => onReference(chunk)}>引用提问</button></footer>
  </article>;
}

export function ReaderConversation({ messages }: { messages: readonly ReaderMessage[] }) {
  return <>{messages.map(message => <article className={`focus-message${message.role === "assistant" ? " focus-reader__chunk" : ""}`} data-message-id={message.messageId} data-role={message.role} key={message.messageId}>
    <header>{message.role === "user" ? "你" : "Agent"}</header>
    <MarkdownContent text={message.content} sourceId={message.reference?.sourceId} />
  </article>)}</>;
}
