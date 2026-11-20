/// <reference types="vite/client" />
import { useEffect, useMemo, useRef, useState } from "react";
import type { PDFPageProxy, RenderTask, TextLayer } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";

type PDF = NonNullable<ReadingDocument["pdf"]>;
type Block = PDF["blocks"][number];
type Evidence = readonly ValidatedAnswerEvidence[];

function numbers(items: Evidence) {
  return items.map(e => <button key={e.evidenceId} type="button" className="source-evidence-number"
    data-evidence={e.evidenceId} aria-label={`返回回答证据 ${e.displayNumber}`}>{e.displayNumber}</button>);
}

export function TranslatedPaper({ document, evidence }: { document: ReadingDocument; evidence: Evidence }) {
  return <article>{document.translation?.chunks.map(chunk => {
    const items = evidence.filter(e => e.sourceLines[0] <= chunk.sourceLines[1] && chunk.sourceLines[0] <= e.sourceLines[1]);
    return <section key={chunk.id} data-source-line={chunk.sourceLines[0]} data-source-end={chunk.sourceLines[1]}
      data-evidence-block={items.map(e => e.evidenceId).join(" ") || undefined}>
      <MarkdownContent text={chunk.text} sourceId={document.sourceId} />{numbers(items)}
    </section>;
  })}</article>;
}

function Page({ page, blocks, evidence, active }: { page: PDFPageProxy; blocks: readonly Block[]; evidence: Evidence; active?: string }) {
  const element = useRef<HTMLDivElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState(false);
  const viewport = page.getViewport({ scale: 1 });
  useEffect(() => {
    const node = element.current!, surface = canvas.current!;
    let layer: TextLayer | undefined;
    let task: RenderTask | undefined, shown = false, generation = 0;
    async function draw() {
      const revision = ++generation;
      layer?.cancel();
      task?.cancel();
      await task?.promise.catch(() => {});
      if (revision !== generation) return;
      const container = text.current!;
      container.replaceChildren();
      if (!shown) { surface.width = surface.height = 0; return; }
      const base = page.getViewport({ scale: 1 });
      const scale = Math.min(2400 / Math.max(base.width, base.height), node.clientWidth * Math.min(devicePixelRatio || 1, 2) / base.width);
      if (!scale) return;
      const sized = page.getViewport({ scale });
      surface.width = Math.ceil(sized.width); surface.height = Math.ceil(sized.height);
      task = page.render({ canvas: surface, viewport: sized });
      try {
        await task.promise;
        const { TextLayer } = await import("pdfjs-dist");
        if (revision !== generation) return;
        setError(false);
        const display = page.getViewport({ scale: node.clientWidth / base.width });
        container.style.setProperty("--total-scale-factor", String(display.scale * page.userUnit));
        layer = new TextLayer({ textContentSource: page.streamTextContent(), container, viewport: display });
        await layer.render();
      }
      catch { if (revision === generation) setError(true); }
    }
    const resize = new ResizeObserver(() => { if (shown) void draw(); });
    resize.observe(node);
    const observer = new IntersectionObserver(([entry]) => { shown = entry.isIntersecting; void draw(); }, { rootMargin: "700px" });
    observer.observe(node);
    return () => { generation++; observer.disconnect(); resize.disconnect(); layer?.cancel(); task?.cancel(); };
  }, [page]);
  return <div className="paper-pdf-page" data-pdf-page={page.pageNumber} ref={element} style={{ aspectRatio: `${viewport.width}/${viewport.height}` }} aria-label={`第 ${page.pageNumber} 页`}>
    <canvas ref={canvas} aria-label={`原版 PDF 第 ${page.pageNumber} 页`} />
    <div ref={text} className="paper-text" />
    {error && <span role="alert">此页渲染失败</span>}
    {blocks.map(block => {
      const items = evidence.filter(e => e.blockIds?.includes(block.blockId));
      const box = block.bbox;
      return <div key={block.blockId} className="paper-region" data-block-id={block.blockId}
        data-source-line={block.sourceLines[0]} data-source-end={block.sourceLines[1]}
        data-evidence-block={items.map(e => e.evidenceId).join(" ") || undefined} data-page-only={!box}
        data-active={items.some(e => e.evidenceId === active)}
        style={box ? { left: box[0]*100+"%", top: box[1]*100+"%", width: (box[2]-box[0])*100+"%", height: (box[3]-box[1])*100+"%" } : { top: 0, right: 0 }}>
        {numbers(items)}
      </div>;
    })}
  </div>;
}

export function OriginalPaper({ url, pdf, evidence, active, onReady }: { url: string; pdf: PDF; evidence: Evidence; active?: string; onReady: () => void }) {
  const [pages, setPages] = useState<PDFPageProxy[]>([]), [error, setError] = useState("");
  useEffect(() => {
    let live = true, dispose: (() => void) | undefined;
    setPages([]); setError("");
    async function load() {
      const lib = await import("pdfjs-dist");
      if (!live) return;
      lib.GlobalWorkerOptions.workerSrc = workerUrl;
      const task = lib.getDocument({ url, isEvalSupported: false, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/", wasmUrl: "/pdfjs/wasm/", iccUrl: "/pdfjs/iccs/" });
      dispose = () => { void task.destroy(); };
      const doc = await task.promise;
      const loaded = await Promise.all(Array.from({ length: doc.numPages }, (_, i) => doc.getPage(i + 1)));
      if (live) setPages(loaded);
    }
    void load().catch(() => { if (live) setError("PDF 加载失败"); });
    return () => { live = false; dispose?.(); };
  }, [url]);
  useEffect(() => { if (pages.length) onReady(); }, [pages, onReady]);
  const items = evidence.filter(e => e.layoutVersion === pdf.version);
  const grouped = useMemo(() => {
    const grouped = new Map<number, Map<string, Block>>();
    for (const block of pdf.blocks) {
      const blocks = grouped.get(block.page) ?? new Map<string, Block>();
      const previous = blocks.get(block.blockId);
      blocks.set(block.blockId, previous ? { ...previous, sourceLines: [
        Math.min(previous.sourceLines[0], block.sourceLines[0]), Math.max(previous.sourceLines[1], block.sourceLines[1]),
      ] } : block);
      grouped.set(block.page, blocks);
    }
    return grouped;
  }, [pdf]);
  return <div className="paper-pages">{error ? <p role="alert">{error} · <a href={url} target="_blank" rel="noreferrer">打开原件</a></p> :
    !pages.length ? <span role="status">加载原版 PDF…</span> : pages.map(page =>
      <Page key={page.pageNumber} page={page} blocks={[...(grouped.get(page.pageNumber)?.values() ?? [])]} evidence={items} active={active} />)}</div>;
}
