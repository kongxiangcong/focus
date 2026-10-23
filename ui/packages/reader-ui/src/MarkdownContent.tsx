import { memo, useContext, useLayoutEffect, useMemo, useRef } from "react";
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
  table: ({ children }) => <div className="focus-table" tabIndex={0}><table>{children}</table></div>,
  td: ({ children, colSpan, rowSpan }) => <td colSpan={colSpan} rowSpan={rowSpan}>{children}</td>,
  th: ({ children, colSpan, rowSpan }) => <th colSpan={colSpan} rowSpan={rowSpan}>{children}</th>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  img: ({ src, alt }) => <img src={src} alt={alt ?? ""} loading="lazy" />,
};
export const MarkdownContent = memo(function MarkdownContent({ text, sourceId, figures, onFigure, inlineFigures = false, marks, annotation, onAnnotations }: {
  text: string; sourceId?: string; figures?: readonly Figure[]; onFigure?: (figure: Figure) => void; inlineFigures?: boolean;
  marks?: readonly RenderMark[];
  annotation?: MarkdownAnnotationInput;
  onAnnotations?: (marks: readonly ResolvedMark[], lost: readonly Located[], text: string) => void;
}) {
  const instanceId = useContext(AssetInstanceContext);
  const markdown = normalizeMathMarkdown(text);
  function markFigures() {
    return (tree: FigureNode) => {
      if (!sourceId || !figures || !onFigure) return;
      for (const { node, id } of scanFigures(tree, sourceId, inlineFigures, markdown).nodes) {
        const figure = figures.find(f => f.id === id);
        if (figure) node.data = { ...node.data, readerFigure: figure };
      }
    };
  }
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
  return <div className="focus-markdown"><Markdown remarkPlugins={remarkPlugins} rehypePlugins={[...rehypePlugins, markFigures, ...annotationPlugins, ...(annotation ? [probe] : [])]}
    components={{ ...components, img: ({ node, src, alt }) => {
      const figure = (node as FigureNode | undefined)?.data?.readerFigure;
      return figure && onFigure ? <button data-anno-ui="" className="reader-figure-link" onClick={() => onFigure(figure)}>查看{figure.label}</button> : <img src={src} alt={alt ?? ""} loading="lazy" />;
    } }} urlTransform={(url, key) => {
      if (sourceId && key === "src") return imageUrl(url, sourceId, instanceId);
      return defaultUrlTransform(url);
    }}>{markdown}</Markdown></div>;
});
