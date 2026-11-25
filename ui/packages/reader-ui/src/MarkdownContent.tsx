import { rehypeSourceEvidence } from "./source-evidence";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { useCallback, memo, useContext, useLayoutEffect, useMemo, useRef } from "react";
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

export interface MarkdownAnnotationInput {
  located: readonly Located[]; layer: AnnotationLayer; pending?: PendingAnnotation | null;
  fresh?: Record<string, ("hl" | "note")[]>;
}

const components: Components = {
  table: ({ node, children }) => <div className="focus-table" tabIndex={0}
    data-source-line={node?.properties.dataSourceLine} data-evidence-block={node?.properties.dataEvidenceBlock}>
    <table>{children}</table>
  </div>,
  td: ({ children, colSpan, rowSpan }) => <td colSpan={colSpan} rowSpan={rowSpan}>{children}</td>,
  th: ({ children, colSpan, rowSpan }) => <th colSpan={colSpan} rowSpan={rowSpan}>{children}</th>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  img: ({ src, alt }) => <img src={src} alt={alt ?? ""} loading="lazy" />,
};
export const MarkdownContent = memo(function MarkdownContent({ text, sourceId, figures, onFigure, inlineFigures = false, marks, annotation, onAnnotations, sourceEvidence, onCitation, onCitationHover, activeCitation }: {
  text: string; sourceId?: string; figures?: readonly Figure[]; onFigure?: (figure: Figure) => void; inlineFigures?: boolean;
  activeCitation?: string;
  onCitationHover?: (id: string | undefined) => void;
  onCitation?: (id: string, keyboard: boolean, origin: HTMLButtonElement) => void;
  sourceEvidence?: { document: ReadingDocument; evidence: readonly ValidatedAnswerEvidence[]; active?: string };
  marks?: readonly RenderMark[];
  annotation?: MarkdownAnnotationInput;
  onAnnotations?: (marks: readonly ResolvedMark[], lost: readonly Located[], text: string) => void;
}) {
  const citationRef = useRef(onCitation); citationRef.current = onCitation;
  const activeCitationRef = useRef(activeCitation); activeCitationRef.current = activeCitation;
  const hoverRef = useRef(onCitationHover); hoverRef.current = onCitationHover;
  // Stable component identity prevents hover/focus updates from replacing the focused button.
  const renderLink = useMemo<Components["a"]>(() => ({ children, href }) => href?.startsWith("#e-") && citationRef.current ?
    <button className="answer-evidence-number" data-citation={href.slice(3)} data-answer-target={activeCitationRef.current === href.slice(3) || undefined} onPointerEnter={() => hoverRef.current?.(href.slice(3))} onPointerLeave={() => hoverRef.current?.(undefined)} onFocus={() => hoverRef.current?.(href.slice(3))} onBlur={() => hoverRef.current?.(undefined)} onClick={event => { event.stopPropagation(); citationRef.current?.(href.slice(3), event.detail === 0, event.currentTarget); }}>{children}</button> : <a href={href} target="_blank" rel="noreferrer">{children}</a>, []);
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
        sourceEvidence.evidence.map(e => [e.evidenceId, e.messageId, e.sourceLines, e.quote, e.displayNumber, e.renderGranularity]),
      ])
    : "";
  const evidenceById = useMemo(() => new Map(sourceEvidence?.evidence.map(item => [item.evidenceId, item])), [evidenceKey]);
  const evidencePlugins = useMemo(() => sourceEvidence ? [[rehypeSourceEvidence, sourceEvidence] as [typeof rehypeSourceEvidence, typeof sourceEvidence]] : [], [evidenceKey]);
  const markKey = JSON.stringify(marks ?? []);
  const annotationPlugins = useMemo(() => marks?.length ? [[rehypeAnnotations, { items: marks }] as [typeof rehypeAnnotations, { items: readonly RenderMark[] }]] : [], [markKey]);
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
      rehypeAnnotations({ items })(tree);
    };
  }, [annotationKey]);
  useLayoutEffect(() => {
    if (annotation && resultRef.current) onAnnotations?.(resultRef.current.marks, resultRef.current.lost, resultRef.current.text);
  }, [annotationKey, text, onAnnotations]);
  // Parent handlers may change on each token; retain the parsed tree for stable content.
  const rendered = useMemo(() => <Markdown remarkPlugins={remarkPlugins} rehypePlugins={[...rehypePlugins, markFigures, ...evidencePlugins, ...annotationPlugins, ...(annotation ? [probe] : [])]}
    components={{ ...components, a: renderLink, span: ({ node, ...props }) => {
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
  return <div className="focus-markdown">{rendered}</div>;
});
