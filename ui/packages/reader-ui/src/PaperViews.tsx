/// <reference types="vite/client" />
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask, TextLayer } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PdfBox, ReadingDocument, SourceScope, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";

type PDF = NonNullable<ReadingDocument["pdf"]>;
type PageSize = NonNullable<PDF["pages"]>[number];
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

export function boxesForBlock(block: Block): readonly PdfBox[] {
  return block.bboxes ?? (block.bbox ? [block.bbox] : []);
}

export function matchesPdfLayout(evidence: ValidatedAnswerEvidence, scope: SourceScope, pdf: PDF) {
  return evidence.sourceId === scope.sourceId && evidence.bundleVersion === scope.bundleVersion &&
    evidence.layoutVersion === pdf.version;
}

function PaperSurface({ page, element }: { page: PDFPageProxy; element: RefObject<HTMLDivElement | null> }) {
  const text = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const node = element.current!, surface = canvas.current!;
    let layer: TextLayer | undefined;
    let task: RenderTask | undefined, shown = true, generation = 0;
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
      try {
        task = page.render({ canvas: surface, viewport: sized });
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
  }, [element, page]);
  return <>
    <canvas ref={canvas} aria-label={`原版 PDF 第 ${page.pageNumber} 页`} />
    <div ref={text} className="paper-text" />
    {error && <span role="alert">此页渲染失败</span>}
  </>;
}

function Page({ document, pageNumber, size, blocks, evidence, active }: {
  document: PDFDocumentProxy; pageNumber: number; size?: PageSize; blocks: readonly Block[];
  evidence: Evidence; active?: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState<PDFPageProxy>();
  const [error, setError] = useState(false);

  useEffect(() => {
    const node = element.current;
    if (!node) return;
    let live = true;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      void document.getPage(pageNumber).then(loaded => {
        if (live) setPage(loaded);
      }, () => {
        if (live) setError(true);
      });
    }, { rootMargin: "700px" });
    observer.observe(node);
    return () => { live = false; observer.disconnect(); };
  }, [document, pageNumber]);

  const viewport = page?.getViewport({ scale: 1 });
  const width = viewport?.width ?? size?.width;
  const height = viewport?.height ?? size?.height;
  const canDrawBoxes = !error && (!viewport || !size?.width || !size.height || (
    Math.abs(viewport.width - size.width) < 0.1 && Math.abs(viewport.height - size.height) < 0.1 &&
    (size.rotation == null || viewport.rotation === size.rotation)
  ));
  const pageBlocks = blocks.filter(block => !canDrawBoxes || !boxesForBlock(block).length);
  const pageEvidence = evidence.filter(item => pageBlocks.some(block => item.blockIds?.includes(block.blockId)));
  return <div className="paper-pdf-page" data-pdf-page={pageNumber} ref={element}
    style={{ aspectRatio: width && height ? `${width}/${height}` : undefined }} aria-label={`第 ${pageNumber} 页`}>
    {page && <PaperSurface page={page} element={element} />}
    {error && <span role="alert">此页渲染失败</span>}
    {canDrawBoxes && blocks.flatMap(block => {
      const items = evidence.filter(item => item.blockIds?.includes(block.blockId));
      return boxesForBlock(block).map((box, index) => (
        <div key={`${block.blockId}:${index}`} className="paper-region" data-block-id={block.blockId}
          data-source-line={block.sourceLines[0]} data-source-end={block.sourceLines[1]}
          data-evidence-block={items.map(item => item.evidenceId).join(" ") || undefined}
          data-active={items.some(item => item.evidenceId === active)}
          style={{ left: box[0] * 100 + "%", top: box[1] * 100 + "%", width: (box[2] - box[0]) * 100 + "%",
            height: (box[3] - box[1]) * 100 + "%" }}>
          {index === 0 && numbers(items)}
        </div>
      ));
    })}
    {pageBlocks.length > 0 && <div className="paper-region paper-page-markers" data-page-only="true"
      data-evidence-block={pageEvidence.map(item => item.evidenceId).join(" ") || undefined}
      data-active={pageEvidence.some(item => item.evidenceId === active)}>
      {pageBlocks.map(block => <span key={block.blockId} data-block-id={block.blockId}
        data-source-line={block.sourceLines[0]} data-source-end={block.sourceLines[1]} />)}
      {numbers(pageEvidence)}
    </div>}
  </div>;
}

export function OriginalPaper({ url, pdf, sourceId, bundleVersion, evidence, active, onReady, onUnavailable }: SourceScope & {
  url: string; pdf: PDF; evidence: Evidence; active?: string; onReady: () => void; onUnavailable?: () => void;
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
      dispose = () => { void task.destroy(); };
      const document = await task.promise;
      if (live) setLoaded({ url, document });
    }
    void load().catch(() => { if (live) setLoaded({ url }); });
    return () => { live = false; dispose?.(); };
  }, [url]);
  useEffect(() => {
    if (document) onReady();
    else if (error) onUnavailable?.();
  }, [document, error, onReady, onUnavailable]);
  const items = useMemo(() => evidence.filter(item => matchesPdfLayout(item, { sourceId, bundleVersion }, pdf)),
    [evidence, sourceId, bundleVersion, pdf]);
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
        blocks={[...(grouped.get(pageNumber)?.values() ?? [])]} evidence={items} active={active} />;
    })}</div>;
}
