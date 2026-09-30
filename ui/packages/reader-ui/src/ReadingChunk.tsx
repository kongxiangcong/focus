import type { ReaderChunk, ReaderImage, ReaderMessage } from "@focus/reader-contracts";
import { useState } from "react";
import { MarkdownContent } from "./MarkdownContent";
import { chunkFigures, extractFigures, imageIdentity, type Figure } from "./figures";

export const chunkKey = (c: { sourceId: string; planId: string; chunkId: string }) => `${c.sourceId}/${c.planId}/${c.chunkId}`;

export function ReadingChunk({ chunk, onReference, onFigure, onLanguage }: { chunk: ReaderChunk; onReference: (chunk: ReaderChunk) => void;
  onFigure?: (figure: Figure) => void; onLanguage?: (chunk: ReaderChunk, original: boolean) => void }) {
  const [original, setOriginal] = useState(false);
  const translated = chunk.translation !== null && !original;
  const preparing = !original && chunk.presentationStatus === "translation-required" && chunk.translation === null;
  const text = preparing ? "" : translated ? chunk.translation! : chunk.sourceMarkdown;
  const figures = chunkFigures(chunk, original);
  return <article className="focus-reading focus-reader__chunk" data-chunk-key={chunkKey(chunk)}>
    <header className="focus-reading__meta"><span>{preparing ? "待准备" : translated ? "译文" : "原文"}</span><span>第 {chunk.index} / {chunk.total} 段</span>
      {chunk.translation !== null && <button aria-pressed={original} onClick={() => { setOriginal(!original); onLanguage?.(chunk, !original); }}>{original ? "查看译文" : "查看原文"}</button>}
    </header>
    <h2>{chunk.sectionPath.at(-1)}</h2>
    {preparing ? <p role="status">译文尚未准备完成，请打开材料继续准备。</p> : <MarkdownContent text={text} sourceId={chunk.sourceId} figures={figures} onFigure={onFigure} />}
    {!preparing && onFigure && figures.filter(i => !extractFigures(text, chunk.sourceId).found.some(image => imageIdentity(image.src, chunk.sourceId) === i.id)).map(i =>
      <button className="reader-figure-link" key={i.id} onClick={() => onFigure(i)}>查看{i.label}</button>)}
    {!preparing && !onFigure && chunk.images.filter(i => !text.includes(i.src) && !text.includes(decodeURIComponent(i.src.split('/').at(-1)!))).map(i =>
      <figure key={i.src}><img src={i.src} alt={i.caption} loading="lazy" /><figcaption>{i.caption}</figcaption></figure>)}
    <footer><button onClick={() => onReference(chunk)}>引用提问</button></footer>
  </article>;
}

const figureNumber = /(?:图|fig(?:ure)?\.?)\s*[-.:：]?\s*(\d+[a-z]?)(?!\d)/gi;
function referencedFigures(message: ReaderMessage, chunks: readonly ReaderChunk[], figures: readonly ReaderImage[], figureSourceId?: string): ReaderImage[] {
  const sourceId = message.sourceId ?? message.reference?.sourceId;
  if (message.role !== "assistant" || message.sourceDeleted || !sourceId) return [];
  const numbers = new Set([...message.content.matchAll(figureNumber)].map(match => match[1].toLowerCase()));
  if (!numbers.size) return [];
  const seen = new Set<string>();
  const available = [...chunks.filter(chunk => chunk.sourceId === sourceId).flatMap(chunk => chunk.images),
    ...(sourceId === figureSourceId ? figures : [])];
  return available.filter(image => {
    const match = image.caption.match(/^\s*(?:图|fig(?:ure)?\.?)\s*[-.:：]?\s*(\d+[a-z]?)(?!\d)/i);
    if (!match || !numbers.has(match[1].toLowerCase()) || seen.has(image.src)) return false;
    seen.add(image.src);
    // An image already included in the answer's Markdown is rendered in place.
    return ![...message.content.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)].some(link =>
      link[1] === image.src || image.src.endsWith("/" + link[1].replace(/^\.\//, "")));
  });
}

export function ReaderConversation({ messages, chunks = [], figures = [], figureSourceId, sourceFigures = [], onFigure }: {
  messages: readonly ReaderMessage[]; chunks?: readonly ReaderChunk[]; figures?: readonly ReaderImage[]; figureSourceId?: string;
  sourceFigures?: readonly Figure[]; onFigure?: (figure: Figure) => void;
}) {
  return <>{messages.map(message => <article className={`focus-message${message.role === "assistant" ? " focus-reader__chunk" : ""}`} data-message-id={message.messageId} data-role={message.role} key={message.messageId}>
    <header>{message.role === "user" ? "你" : "Agent"}{message.sourceDeleted && <small> · 来源已删除</small>}</header>
    <MarkdownContent text={message.content} sourceId={message.sourceDeleted ? undefined : message.sourceId ?? message.reference?.sourceId}
      figures={sourceFigures} onFigure={onFigure} inlineFigures />
    {referencedFigures(message, chunks, figures, figureSourceId).map(image => {
      const figure = sourceFigures.find(f => f.id === imageIdentity(image.src, message.sourceId ?? message.reference?.sourceId ?? ""));
      return onFigure && figure ? <button className="reader-figure-link" key={figure.id} onClick={() => onFigure(figure)}>查看{figure.label}</button> : <figure key={image.src} className="focus-referenced-figure">
      <img src={image.src} alt={image.caption} loading="lazy" /><figcaption>{image.caption}</figcaption>
    </figure>;
    })}
  </article>)}</>;
}
