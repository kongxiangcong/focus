import { AssetInstanceContext } from "./asset-context";
import { withAssetInstance } from "./figures";
import type { AnnotationLayer, ReaderChunk, ReaderImage, ReaderMessage, SourceNote, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { useCallback, useContext, useEffect, useId, useMemo, useState, type ReactNode, type Ref } from "react";
import { MarkdownContent } from "./MarkdownContent";
import { answerEvidenceKey, citedMarkdown, messageEvidence } from "./source-evidence";
import type { Located, PendingAnnotation, ResolvedMark } from "./annotation-projection";
import { chunkFigures, imageIdentity, type Figure } from "./figures";
import { chunkNoteMarks } from "./selected-source-note";

export const chunkKey = (c: { sourceId: string; planId: string; chunkId: string }) => `${c.sourceId}/${c.planId}/${c.chunkId}`;

export function ReadingChunk({ chunk, onReference, onFigure, onZoom, onLanguage, located, pending, fresh, onLayerChange, onMarks, sharedNotes, evidence = [], onEvidence, bodyRef, afterBody }: { chunk: ReaderChunk; onReference: (chunk: ReaderChunk) => void;
  onZoom?: (figure: Figure, origin: HTMLElement) => void; onFigure?: (figure: Figure) => void; onLanguage?: (chunk: ReaderChunk, original: boolean) => void;
  located?: readonly Located[]; pending?: PendingAnnotation | null; fresh?: Record<string, ("hl" | "note")[]>;
  sharedNotes?: readonly SourceNote[];
  evidence?: readonly ValidatedAnswerEvidence[];
  onEvidence?: (item: ValidatedAnswerEvidence) => void;
  bodyRef?: Ref<HTMLDivElement>;
  afterBody?: ReactNode;
  onLayerChange?: (chunk: ReaderChunk, layer: AnnotationLayer) => void;
  onMarks?: (key: string, marks: readonly ResolvedMark[], lost: readonly Located[], layer: AnnotationLayer, text: string) => void;
}) {
  const instanceId = useContext(AssetInstanceContext);
  const [original, setOriginal] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const evidenceListId = useId();
  const translated = chunk.translation !== null && !original;
  const preparing = !original && chunk.presentationStatus === "translation-required" && chunk.translation === null;
  const text = preparing ? "" : translated ? chunk.translation! : chunk.sourceMarkdown;
  const figures = chunkFigures(chunk, original);
  const layer: AnnotationLayer = translated ? "translation" : "source";
  const key = chunkKey(chunk);
  const annotation = useMemo(() => located || pending || onMarks ? { located: located ?? [], pending, fresh, layer } : undefined, [located, pending, fresh, layer, onMarks]);
  const marks = useMemo(() => sharedNotes ? chunkNoteMarks(chunk, layer, sharedNotes) : [], [chunk, layer, sharedNotes]);
  const reportMarks = useCallback((marks: readonly ResolvedMark[], lost: readonly Located[], text: string) => onMarks?.(key, marks, lost, layer, text), [key, layer, onMarks]);
  useEffect(() => { onLayerChange?.(chunk, layer); }, [chunk, layer, onLayerChange]);
  return <article className="focus-reading focus-reader__chunk" data-chunk-key={chunkKey(chunk)} data-annotation-layer={layer}>
    <header className="focus-reading__meta"><span>{preparing ? "待准备" : translated ? "译文" : "原文"}</span><span>第 {chunk.index} / {chunk.total} 段</span>
      {chunk.translation !== null && <button aria-pressed={original} onClick={() => { setOriginal(!original); onLanguage?.(chunk, !original); }}>{original ? "查看译文" : "查看原文"}</button>}
    </header>
    <h2>{chunk.sectionPath.at(-1)}</h2>
    {preparing ? <p role="status">译文尚未准备完成，请打开材料继续准备。</p> : <>
      <MarkdownContent text={text} sourceId={chunk.sourceId} figures={figures} onFigure={onFigure} marks={marks} annotation={annotation} onAnnotations={reportMarks} bodyRef={bodyRef} />
      {afterBody}
    </>}
    {!preparing && onFigure && <div className="reader-thumbnail-strip">{figures.map(f => <div className="reader-thumbnail" key={f.id}>
      <button aria-label={`放大${f.label}`} onClick={e => onZoom?.(f, e.currentTarget)}><img src={withAssetInstance(f.src, instanceId)} alt={f.caption || f.label} width={92} height={58} loading="lazy" /></button>
      <div><strong>{f.label}</strong><p title={f.caption}>{f.caption}</p><button onClick={() => onFigure(f)}>在资料栏固定</button></div>
    </div>)}</div>}
    {!preparing && !onFigure && chunk.images.filter(i => !text.includes(i.src) && !text.includes(decodeURIComponent(i.src.split('/').at(-1)!))).map(i =>
      <figure key={i.src}><img src={withAssetInstance(i.src, instanceId)} alt={i.caption} loading="lazy" /><figcaption>{i.caption}</figcaption></figure>)}
    <footer><button onClick={() => onReference(chunk)}>引用提问</button>
      {!!evidence.length && onEvidence && <div className="reading-chunk-evidence">
        <button type="button" aria-expanded={showEvidence} aria-controls={evidenceListId} onClick={() => setShowEvidence(open => !open)}>
          对话证据 · {evidence.length} 条
        </button>
        <ul id={evidenceListId} hidden={!showEvidence}>{evidence.map(item => <li key={answerEvidenceKey(item)}>
          <button type="button" onClick={() => onEvidence(item)}>
            <span>证据 {item.displayNumber}</span><span>{item.quote.exact}</span>
          </button>
        </li>)}</ul>
      </div>}
    </footer>
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
    return true;
  });
}

export function ReaderConversation({ messages, chunks = [], figures = [], figureSourceId, sourceFigures = [], onFigure, onZoom, streaming, onJump, onHighlight, onClearHighlight, onSaveNote, discussionId, onEvidence, hideEvidence }: {
  messages: readonly ReaderMessage[]; chunks?: readonly ReaderChunk[]; figures?: readonly ReaderImage[]; figureSourceId?: string;
  onZoom?: (figure: Figure, origin: HTMLElement) => void;
  streaming?: boolean;
  onJump?: (chunk: ReaderChunk, excerpt?: string) => void;
  onHighlight?: (chunk: ReaderChunk, excerpt: string) => void; onClearHighlight?: () => void;
  onSaveNote?: (message: ReaderMessage, chunk?: ReaderChunk) => void;
  discussionId?: string;
  onEvidence?: (item: ValidatedAnswerEvidence) => void;
  hideEvidence?: boolean;
  sourceFigures?: readonly Figure[]; onFigure?: (figure: Figure) => void;
}) {
  const instanceId = useContext(AssetInstanceContext);
  return <>{messages.map(message => {
    const reference = chunks.find(c => c.sourceId === (message.reference?.sourceId ?? message.sourceId) && c.chunkId === (message.reference?.chunkId ?? message.chunkId));
    const sourceId = message.sourceId ?? message.reference?.sourceId;
    const refs = message.role === "assistant" && sourceId && !message.sourceDeleted
      ? messageEvidence(message, { sourceId }, discussionId ?? message.discussionId) : [];
    const markdown = message.role === "assistant" ? citedMarkdown(message, refs, hideEvidence) : message.content;
    const excerpt = message.content.startsWith("> ") ? message.content.split("\n\n")[0].replace(/^> /gm, "") : (reference?.translation ?? reference?.sourceMarkdown ?? "").replace(/[#*`]/g, "").split(/[。！？\n]/).find(s => s.trim() && !s.includes("!["))?.slice(0, 100) ?? "";
    return <article className={`focus-message${message.role === "assistant" ? " focus-reader__chunk" : ""}`} data-message-id={message.messageId} data-role={message.role} key={message.messageId}>
    <header>{message.role === "user" ? "你" : "FOCUS"}{message.sourceDeleted && <small> · 来源已删除</small>}</header>
    {message.role === "user" && reference && <button className="reader-quote-bar" onClick={() => onJump?.(reference, excerpt)} onMouseEnter={() => onHighlight?.(reference, excerpt)} onMouseLeave={onClearHighlight} onFocus={() => onHighlight?.(reference, excerpt)} onBlur={onClearHighlight}><strong>第 {reference.index} 段</strong><span>{excerpt}</span></button>}
    <MarkdownContent text={markdown} sourceId={message.sourceDeleted ? undefined : sourceId}
      onCitation={refs.length && onEvidence ? id => { const evidence = refs.find(item => item.evidenceId === id); if (evidence) onEvidence(evidence); } : undefined}
      figures={sourceFigures} onFigure={onZoom ? f => onZoom(f, document.activeElement as HTMLElement) : onFigure} inlineFigures />
    {referencedFigures(message, chunks, figures, figureSourceId).map(image => {
      const figure = sourceFigures.find(f => f.id === imageIdentity(image.src, message.sourceId ?? message.reference?.sourceId ?? ""));
      return onFigure && figure ? <button className="reader-answer-thumbnail" aria-label={`放大${figure.label}`} key={figure.id} onClick={e => onZoom ? onZoom(figure, e.currentTarget) : onFigure(figure)}><img src={withAssetInstance(figure.src, instanceId)} alt={figure.caption || figure.label} loading="lazy" /><span>{figure.label}</span></button> : <figure key={image.src} className="focus-referenced-figure">
      <img src={withAssetInstance(image.src, instanceId)} alt={image.caption} loading="lazy" /><figcaption>{image.caption}</figcaption>
    </figure>;
    })}
    {message.role === "assistant" && (streaming ? <span className="reader-stream-block" aria-label="回答生成中" /> : <footer className="reader-answer-actions"><button onClick={() => onSaveNote?.(message, reference)}>存为笔记</button><button onClick={() => void navigator.clipboard?.writeText(message.content)}>复制</button>{reference && <button onClick={() => onJump?.(reference)}>回看第 {reference.index} 段</button>}</footer>)}
  </article>})}</>;
}
