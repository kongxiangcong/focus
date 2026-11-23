/// <reference types="vite/client" />
import { type RefObject, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask, TextLayer } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PdfBox, ReadingDocument } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { PaperEvidence, PaperPdf as PDF } from "./paper-evidence";
type PageSize = NonNullable<PDF["pages"]>[number];
type Block = PDF["blocks"][number];
export type PdfPageState = "ready" | "unavailable";

export function TranslatedPaper({ document, evidence }: { document: ReadingDocument; evidence: readonly PaperEvidence[] }) {
  return <article>{document.translation?.chunks.map(chunk => {
    const items = evidence.filter(item => item.translationChunks.includes(chunk.id)).map(item => item.evidence);
    return <section key={chunk.id} data-translation-chunk={chunk.id} data-source-line={chunk.sourceLines[0]} data-source-end={chunk.sourceLines[1]}
      data-evidence-block={items.map(e => e.evidenceId).join(" ") || undefined}>
      <SourceEvidenceMarkers items={items} /><MarkdownContent text={chunk.text} sourceId={document.sourceId} />
    </section>;
  })}</article>;
}

export function boxesForBlock(block: Block): readonly PdfBox[] {
  return block.bboxes ?? (block.bbox ? [block.bbox] : []);
}

function PaperSurface({ page, element }: { page: PDFPageProxy; element: RefObject<HTMLDivElement | null> }) {
  const text = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const node = element.current!, surface = canvas.current!;
    let layer: TextLayer | undefined;
    let task: RenderTask | undefined;
    let live = true, shown = false, drawing = false, lastWidth = -1;
    async function draw() {
      if (!live || drawing) return;
      const width = shown ? node.clientWidth : 0;
      if (width === lastWidth) return;
      lastWidth = width;
      const container = text.current!;
      container.replaceChildren();
      if (!width) { surface.width = surface.height = 0; return; }
      const base = page.getViewport({ scale: 1 });
      const scale = Math.min(2400 / Math.max(base.width, base.height), width * Math.min(devicePixelRatio || 1, 2) / base.width);
      const sized = page.getViewport({ scale });
      surface.width = Math.ceil(sized.width); surface.height = Math.ceil(sized.height);
      drawing = true;
      try {
        task = page.render({ canvas: surface, viewport: sized });
        await task.promise;
        const { TextLayer } = await import("pdfjs-dist");
        if (!live) return;
        const display = page.getViewport({ scale: width / base.width });
        container.style.setProperty("--total-scale-factor", String(display.scale * page.userUnit));
        layer = new TextLayer({ textContentSource: page.streamTextContent(), container, viewport: display });
        await layer.render();
        if (live) setError(false);
      } catch {
        if (live) setError(true);
      } finally {
        drawing = false;
        if (live) void draw();
      }
    }
    const resize = new ResizeObserver(() => void draw());
    resize.observe(node);
    const observer = new IntersectionObserver(entries => {
      shown = entries.at(-1)?.isIntersecting ?? false;
      void draw();
    }, { root: node.closest(".source-original"), rootMargin: "700px" });
    observer.observe(node);
    return () => { live = false; observer.disconnect(); resize.disconnect(); layer?.cancel(); task?.cancel(); };
  }, [element, page]);
  return <>
    <canvas ref={canvas} aria-label={`原版 PDF 第 ${page.pageNumber} 页`} />
    <div ref={text} className="paper-text" />
    {error && <span role="alert">此页渲染失败</span>}
  </>;
}

function Page({ document, pageNumber, size, blocks, evidence, active, requested, onPageSettled }: {
  document: PDFDocumentProxy; pageNumber: number; size?: PageSize; blocks: readonly Block[];
  evidence: readonly PaperEvidence[]; active?: string; requested: boolean;
  onPageSettled: (page: number, state: PdfPageState) => void;
}) {
  const element = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState<PDFPageProxy>();
  const [error, setError] = useState<"browse" | "navigation">();
  const [nearby, setNearby] = useState(false);
  const navigationLoad = useRef(false);

  useEffect(() => {
    const node = element.current;
    if (!node) return;
    const observer = new IntersectionObserver(entries => {
      if (!entries.at(-1)?.isIntersecting) return;
      observer.disconnect();
      setNearby(true);
    }, { rootMargin: "700px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const loadPage = nearby || requested;
  useEffect(() => {
    if (!loadPage) return;
    let live = true;
    if (!nearby) navigationLoad.current = true;
    void document.getPage(pageNumber).then(loaded => {
      if (live) setPage(loaded);
    }, () => {
      if (live) setError(navigationLoad.current ? "navigation" : "browse");
    });
    // A speculative destination can later become nearby. Its failure still
    // belongs to the navigation that requested it, not to passive browsing.
    return () => { live = false; };
  }, [document, pageNumber, loadPage]);

  const viewport = page?.getViewport({ scale: 1 });
  const width = viewport?.width ?? size?.width;
  const height = viewport?.height ?? size?.height;
  const canDrawBoxes = !error && (!viewport || !size?.width || !size.height || (
    Math.abs(viewport.width - size.width) < 0.1 && Math.abs(viewport.height - size.height) < 0.1 &&
    (size.rotation == null || viewport.rotation === size.rotation)
  ));
  useLayoutEffect(() => {
    if (page || error) onPageSettled(pageNumber, canDrawBoxes ? "ready" : "unavailable");
  }, [page, error, onPageSettled, pageNumber, canDrawBoxes]);

  const pageBlocks = blocks.filter(block => !canDrawBoxes || !boxesForBlock(block).length);
  const hasBlock = (item: PaperEvidence, block: Block) => item.pdfBlocks.some(candidate =>
    candidate.page === pageNumber && candidate.blockId === block.blockId);
  const itemsForBlock = (block: Block) => evidence.filter(item => hasBlock(item, block)).map(item => item.evidence);
  const unplaced = evidence.filter(item => !blocks.some(block => hasBlock(item, block))).map(item => item.evidence);
  const pageGroups = pageBlocks.map(block => ({ block, items: itemsForBlock(block) }));
  const pageEvidence = [...unplaced, ...pageGroups.flatMap(group => group.items)];
  return <div className="paper-pdf-page" data-pdf-page={pageNumber} ref={element}
    style={{ aspectRatio: width && height ? `${width}/${height}` : undefined }} aria-label={`第 ${pageNumber} 页`}>
    {page && nearby && <PaperSurface page={page} element={element} />}
    {error === "browse" && <span role="alert">此页渲染失败</span>}
    {canDrawBoxes && blocks.flatMap(block => {
      const items = itemsForBlock(block);
      return boxesForBlock(block).map((box, index) => (
        <div key={`${block.blockId}:${index}`} className="paper-region" data-block-id={block.blockId}
          data-source-line={block.sourceLines[0]} data-source-end={block.sourceLines[1]}
          data-evidence-block={items.map(item => item.evidenceId).join(" ") || undefined}
          data-active={items.some(item => item.evidenceId === active)}
          style={{ left: box[0] * 100 + "%", top: box[1] * 100 + "%", width: (box[2] - box[0]) * 100 + "%",
            height: (box[3] - box[1]) * 100 + "%" }}>
          {index === 0 && <SourceEvidenceMarkers items={items} />}
        </div>
      ));
    })}
    {(pageBlocks.length > 0 || pageEvidence.length > 0) && <div className="paper-region paper-page-markers" data-page-only="true"
      data-evidence-block={pageEvidence.map(item => item.evidenceId).join(" ") || undefined}
      data-active={pageEvidence.some(item => item.evidenceId === active)}>
      {pageGroups.map(({ block, items }) => <span key={block.blockId} data-block-id={block.blockId}
        data-source-line={block.sourceLines[0]} data-source-end={block.sourceLines[1]}>
        <SourceEvidenceMarkers items={items} />
      </span>)}
      <SourceEvidenceMarkers items={unplaced} />
    </div>}
  </div>;
}

export function OriginalPaper({ url, pdf, evidence, active, requestedPages, onReady, onUnavailable, onPageSettled }: {
  url: string; pdf: PDF; evidence: readonly PaperEvidence[]; active?: string; requestedPages?: readonly number[];
  onReady: (count: number) => void; onUnavailable?: () => void;
  onPageSettled: (page: number, state: PdfPageState) => void;
}) {
  const [loaded, setLoaded] = useState<{ url: string; document?: PDFDocumentProxy }>();
  const document = loaded?.url === url ? loaded.document : undefined;
  const error = loaded?.url === url && !document;
  useEffect(() => {
    let live = true;
    let dispose: (() => void) | undefined;
    setLoaded(undefined);
    async function load() {
      const lib = await import("pdfjs-dist");
      if (!live) return;
      lib.GlobalWorkerOptions.workerSrc = workerUrl;
      const task = lib.getDocument({ url, isEvalSupported: false, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/", wasmUrl: "/pdfjs/wasm/", iccUrl: "/pdfjs/iccs/" });
      dispose = () => {
        // PDF.js can reject inside the worker if it is terminated during startup.
        // Give the document a chance to settle, with bounded cleanup for a stalled request.
        let deadline: ReturnType<typeof setTimeout> | undefined;
        const waitLimit = new Promise<void>(resolve => { deadline = setTimeout(resolve, 30_000); });
        const settled = task.promise.then(() => undefined, () => undefined);
        void Promise.race([settled, waitLimit]).then(() => {
          clearTimeout(deadline);
          return task.destroy();
        }).catch(() => {});
      };
      const document = await task.promise;
      if (live) setLoaded({ url, document });
    }
    void load().catch(() => { if (live) setLoaded({ url }); });
    return () => { live = false; dispose?.(); };
  }, [url]);
  useEffect(() => {
    if (document) onReady(document.numPages);
    else if (error) onUnavailable?.();
  }, [document, error, onReady, onUnavailable]);
  const evidenceByPage = useMemo(() => {
    const byPage = new Map<number, PaperEvidence[]>();
    for (const item of evidence) for (const number of item.pdfPages) {
      const items = byPage.get(number) ?? [];
      items.push(item);
      byPage.set(number, items);
    }
    return byPage;
  }, [evidence]);
  const sizes = useMemo(() => new Map(pdf.pages?.map(page => [page.page, page])), [pdf.pages]);
  const grouped = useMemo(() => {
    const grouped = new Map<number, Map<string, Block>>();
    for (const block of pdf.blocks) {
      const blocks = grouped.get(block.page) ?? new Map<string, Block>();
      const previous = blocks.get(block.blockId);
      const bboxes = previous
        ? [...new Map([...boxesForBlock(previous), ...boxesForBlock(block)].map(box => [box.join(","), box])).values()]
        : boxesForBlock(block);
      blocks.set(block.blockId, previous ? { ...previous, bboxes, sourceLines: [
        Math.min(previous.sourceLines[0], block.sourceLines[0]), Math.max(previous.sourceLines[1], block.sourceLines[1]),
      ] } : block);
      grouped.set(block.page, blocks);
    }
    return grouped;
  }, [pdf]);
  return <div className="paper-pages">{error ?
    <p role="alert">PDF 加载失败 · <a href={url} target="_blank" rel="noreferrer">打开原件</a></p> :
    !document ? <span role="status">加载原版 PDF…</span> : Array.from({ length: document.numPages }, (_, index) => {
      const pageNumber = index + 1;
      return <Page key={`${url}:${pageNumber}`} document={document} pageNumber={pageNumber} size={sizes.get(pageNumber)}
        blocks={[...(grouped.get(pageNumber)?.values() ?? [])]} evidence={evidenceByPage.get(pageNumber) ?? []} active={active}
        requested={requestedPages?.includes(pageNumber) ?? false} onPageSettled={onPageSettled} />;
    })}</div>;
}
