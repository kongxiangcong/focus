import { rehypeSourceEvidence } from "./source-evidence";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import { ChunkNoteLinks } from "./ChunkNoteLinks";
import { useCallback, memo, useContext, useLayoutEffect, useMemo, useRef, type Ref } from "react";
import Markdown, { type Components, defaultUrlTransform } from "react-markdown";
import "katex/dist/katex.min.css";
import { AssetInstanceContext } from "./asset-context";
import { imageUrl, scanFigures, type Figure, type FigureNode } from "./figures";
import { normalizeMathMarkdown } from "./math-markdown";
import { remarkPlugins, rehypePlugins } from "./markdown-pipeline";
import { rehypeAnnotations, type RenderMark } from "./rehype-annotations";
import { hastAnnotatableText, type HastNode } from "./annotatable-text";
import { buildMarks, type Located, type PendingAnnotation, type ResolvedMark } from "./annotation-projection";
import type { AnnotationLayer } from "@focus/reader-contracts";
import type { SourceLines } from "./source-position";

export interface MarkdownAnnotationInput {
  located: readonly Located[]; layer: AnnotationLayer; pending?: PendingAnnotation | null;
  fresh?: Record<string, ("hl" | "note")[]>;
}

const components: Components = {
  table: ({ node, children }) => <div className="focus-table" tabIndex={0}
    data-source-line={node?.properties.dataSourceLine} data-source-end={node?.properties.dataSourceEnd}
    data-source-offset-start={node?.properties.dataSourceOffsetStart} data-source-offset-end={node?.properties.dataSourceOffsetEnd}
    data-evidence-block={node?.properties.dataEvidenceBlock}>
    <table>{children}</table>
  </div>,
  td: ({ children, colSpan, rowSpan }) => <td colSpan={colSpan} rowSpan={rowSpan}>{children}</td>,
  th: ({ children, colSpan, rowSpan }) => <th colSpan={colSpan} rowSpan={rowSpan}>{children}</th>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  img: ({ src, alt }) => <img src={src} alt={alt ?? ""} loading="lazy" />,
};

function rehypeSourceExcerpt({ lines: [first, last] }: { lines: SourceLines }) {
  return (tree: HastNode) => {
    // Filter after projecting evidence and notes on the entire original so the
    // excerpt retains the canonical offsets and any Markdown reference definitions.
    tree.children = tree.children?.filter(({ properties }) => properties &&
      (typeof properties.dataSourceEvidenceMarkers === "string" ||
        Number(properties.dataSourceLine) <= last && Number(properties.dataSourceEnd) >= first));
  };
}

export const MarkdownContent = memo(function MarkdownContent({ text, sourceId, figures, onFigure, inlineFigures = false, marks, annotation, onAnnotations, sourceEvidence, onCitation, activeCitation, bodyRef }: {
  text: string; sourceId?: string; figures?: readonly Figure[]; onFigure?: (figure: Figure) => void; inlineFigures?: boolean;
  bodyRef?: Ref<HTMLDivElement>;
  activeCitation?: string;
  onCitation?: (id: string, keyboard: boolean, origin: HTMLButtonElement) => void;
  sourceEvidence?: Parameters<typeof rehypeSourceEvidence>[0] & { excerpt?: SourceLines };
  marks?: readonly RenderMark[];
  annotation?: MarkdownAnnotationInput;
  onAnnotations?: (marks: readonly ResolvedMark[], lost: readonly Located[], text: string) => void;
}) {
  const citationRef = useRef(onCitation); citationRef.current = onCitation;
  const activeCitationRef = useRef(activeCitation); activeCitationRef.current = activeCitation;
  // Stable component identity prevents focus updates from replacing the focused button.
  const renderLink = useMemo<Components["a"]>(() => ({ children, href }) => href?.startsWith("#e-") && citationRef.current ?
    <button className="answer-evidence-number" data-citation={href.slice(3)} data-answer-target={activeCitationRef.current === href.slice(3) || undefined} onClick={event => { event.stopPropagation(); citationRef.current?.(href.slice(3), event.detail === 0, event.currentTarget); }}>{children}</button> : <a href={href} target="_blank" rel="noreferrer">{children}</a>, []);
  const instanceId = useContext(AssetInstanceContext);
  const figureHandler = useRef(onFigure); figureHandler.current = onFigure;
  const showFigure = useCallback((figure: Figure) => figureHandler.current?.(figure), []);
  const markdown = useMemo(() => normalizeMathMarkdown(text), [text]);
  function markFigures() {
    return (tree: FigureNode) => {
      if (!sourceId || !figures || !onFigure) return;
      for (const { node, id } of scanFigures(tree, sourceId, inlineFigures, markdown).nodes) {
        const figure = figures.find(f => f.id === id);
        if (figure) node.data = { ...node.data, readerFigure: figure };
      }
    };
  }
  const evidenceKey = sourceEvidence
    ? JSON.stringify([
        sourceEvidence.document.sourceId,
        sourceEvidence.document.bundleVersion,
        sourceEvidence.excerpt,
        sourceEvidence.evidence.map(e => [e.evidenceId, e.messageId, e.sourceLines, e.quote, e.displayNumber, e.renderGranularity]),
        sourceEvidence.noteLinks,
      ])
    : "";
  const evidenceById = useMemo(() => new Map(sourceEvidence?.evidence.map(item => [item.evidenceId, item])), [evidenceKey]);
  const evidencePlugins = useMemo(() => sourceEvidence ? [[rehypeSourceEvidence, sourceEvidence] as [typeof rehypeSourceEvidence, typeof sourceEvidence]] : [], [evidenceKey]);
  const excerptPlugins = useMemo(() => sourceEvidence?.excerpt
    ? [[rehypeSourceExcerpt, { lines: sourceEvidence.excerpt }] as [typeof rehypeSourceExcerpt, { lines: SourceLines }]] : [], [evidenceKey]);
  const markKey = JSON.stringify(marks ?? []);
  const annotationPlugins = useMemo(() => !annotation && marks?.length ? [[rehypeAnnotations, { items: marks }] as [typeof rehypeAnnotations, { items: readonly RenderMark[] }]] : [], [!!annotation, markKey]);
  const resultRef = useRef<{ marks: readonly ResolvedMark[]; lost: readonly Located[]; text: string } | null>(null);
  const annotationKey = JSON.stringify(annotation);
  const probe = useMemo(() => function annotationProbe() {
    return (tree: HastNode) => {
      if (!annotation) return;
      const text = hastAnnotatableText(tree), result = buildMarks(text, annotation.located, annotation.layer);
      resultRef.current = { ...result, text };
      const items: RenderMark[] = result.marks.map(mark => ({ key: mark.key, start: mark.start, end: mark.end,
        highlightId: mark.highlight?.highlightId, noteId: mark.note?.noteId, fresh: annotation.fresh?.[mark.key],
        ariaLabel: mark.note ? `备注：${mark.note.content.slice(0, 60)}` : "重点" }));
      const pending = annotation.pending;
      if (pending && pending.layer === annotation.layer) {
        const existing = items.find(mark => mark.start === pending.start && mark.end === pending.end);
        if (existing) existing.pending = true;
        else items.push({ key: `p:${pending.requestId ?? `${pending.start}-${pending.end}`}`, start: pending.start, end: pending.end, pending: true, ariaLabel: "正在写备注" });
      }
      rehypeAnnotations({ items: [...items, ...(marks ?? [])] })(tree);
    };
  }, [annotationKey, markKey]);
  useLayoutEffect(() => {
    if (annotation && resultRef.current) onAnnotations?.(resultRef.current.marks, resultRef.current.lost, resultRef.current.text);
  }, [annotationKey, text, onAnnotations]);
  // Parent handlers may change on each token; retain the parsed tree for stable content.
  const rendered = useMemo(() => <Markdown remarkPlugins={remarkPlugins} rehypePlugins={[...rehypePlugins, markFigures, ...evidencePlugins, ...annotationPlugins, ...(annotation ? [probe] : []), ...excerptPlugins]}
    components={{ ...components, a: renderLink, span: ({ node, ...props }) => {
      const chunks = node?.properties.dataSourceChunkNotes;
      if (typeof chunks === "string" && sourceEvidence?.noteLinks) {
        const indices = chunks.split(" ").map(Number);
        return <ChunkNoteLinks links={sourceEvidence.noteLinks.filter(link => indices.includes(link.index))} />;
      }
      const ids = node?.properties.dataSourceEvidenceMarkers;
      if (typeof ids !== "string" || !sourceEvidence) return <span {...props} />;
      const items = ids.split(" ").flatMap(id => evidenceById.get(id) ?? []);
      return <SourceEvidenceMarkers items={items} />;
    }, img: ({ node, src, alt }) => {
      const figure = (node as FigureNode | undefined)?.data?.readerFigure;
      return figure && onFigure ? <button data-anno-ui="" className="reader-figure-link" onClick={() => showFigure(figure)}>查看{figure.label}</button> : <img src={src} alt={alt ?? ""} loading="lazy" />;
    } }} urlTransform={(url, key) => {
      if (sourceId && key === "src") {
        const resolved = imageUrl(url, sourceId, instanceId);
        if (sourceEvidence && resolved.startsWith("/reader/assets/")) {
          const bound = new URL(resolved, "https://focus.invalid");
          bound.searchParams.set("bundle", sourceEvidence.document.bundleVersion);
          return bound.pathname + bound.search + bound.hash;
        }
        return resolved;
      }
      return defaultUrlTransform(url);
    }}>{markdown}</Markdown>, [markdown, activeCitation, sourceId, instanceId, inlineFigures, JSON.stringify(figures), !!onFigure, markKey, annotationKey, evidenceKey, !!onCitation]);
  return <div className="focus-markdown" ref={bodyRef}>{rendered}</div>;
});
