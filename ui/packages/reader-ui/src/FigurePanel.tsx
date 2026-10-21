import { AssetInstanceContext } from "./asset-context";
import { withAssetInstance } from "./figures";
import { useContext, useLayoutEffect, useRef, useState } from "react";
import { MarkdownContent } from "./MarkdownContent";
import type { Figure } from "./figures";

export type ViewerRequest = { figure: Figure; origin: HTMLElement | null };
export function FigurePanel({ figures, selected, onSelect, onZoom, paragraph, onParagraph }: {
  figures: readonly Figure[]; selected: string | null; selectionVersion: number;
  paragraph?: (figure: Figure) => number | undefined; onParagraph?: (figure: Figure) => void;
  onSelect: (figure: Figure) => void; onZoom: (figure: Figure, origin: HTMLElement) => void;
}) {
  const instanceId = useContext(AssetInstanceContext);
  const active = figures.find(f => f.id === selected) ?? figures[0];
  const [failed, setFailed] = useState<string[]>([]);
  return <div className="reader-figure-scroll" tabIndex={0} aria-label="图片浏览">
    {!active && <p>来源尚无可用图片。</p>}
    {active && <figure data-figure-id={active.id} data-selected="true">
      <button className="reader-figure-zoom" aria-label={`放大${active.label}`} onClick={e => onZoom(active, e.currentTarget)}>
        <img src={withAssetInstance(active.src, instanceId)} alt={active.caption || active.label} onError={() => setFailed(old => [...old, active.id])} />
      </button>
      {failed.includes(active.id) && <p role="status">图片加载失败。<a href={active.src} target="_blank" rel="noreferrer">打开原图</a></p>}
      <figcaption><small>{active.label}</small>{active.caption && <MarkdownContent text={active.caption} sourceId={active.sourceId} />}</figcaption>
    </figure>}
    {active && paragraph?.(active) && <button onClick={() => onParagraph?.(active)}>回到第 {paragraph(active)} 段</button>}
    <nav className="reader-figure-grid" aria-label="图片目录">{figures.map(f => <button key={f.id} aria-label={f.label} title={f.caption || f.label} aria-current={active?.id === f.id ? "true" : undefined} onClick={() => onSelect(f)}>
      <img src={withAssetInstance(f.src, instanceId)} alt="" loading="lazy" /><span>{f.label}</span>
    </button>)}</nav>
  </div>;
}
function visible(origin: HTMLElement | null) {
  if (!origin?.isConnected || !origin.checkVisibility?.()) return null;
  const r = origin.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth ? r : null;
}
function delta(from: DOMRect, to: DOMRect) {
  return `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})`;
}
export function FigureViewer({ request, figures, onClose }: { request: ViewerRequest; figures: readonly Figure[]; onClose: () => void }) {
  const instanceId = useContext(AssetInstanceContext);
  const dialog = useRef<HTMLDialogElement>(null), img = useRef<HTMLImageElement>(null);
  const backdrop = useRef<Animation | null>(null);
  const motion = useRef<Animation | null>(null), closing = useRef(false);
  const [figure, setFigure] = useState(request.figure), [natural, setNatural] = useState(false);
  const reduced = () => document.documentElement.dataset.reducedMotion === "true" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  function finish() { dialog.current?.close(); onClose(); if (request.origin?.isConnected) request.origin.focus({ preventScroll: true }); }
  useLayoutEffect(() => {
    dialog.current?.showModal();
    const el = img.current;
    backdrop.current = dialog.current?.animate?.([{ opacity: 0 }, { opacity: 1 }], { duration: reduced() ? 120 : 200, pseudoElement: "::backdrop", fill: "both" }) ?? null;
    if (el?.animate) {
      const from = visible(request.origin?.querySelector('img') ?? request.origin), to = el.getBoundingClientRect();
      motion.current = el.animate(reduced() || !from || !to.width ? [{ opacity: 0 }, { opacity: 1 }] : [{ transform: delta(from, to) }, { transform: "none" }], { duration: reduced() ? 120 : 300, easing: "cubic-bezier(.22,.8,.24,1)", fill: "both" });
    }
    return () => { motion.current?.cancel(); backdrop.current?.cancel(); };
  }, []);
  function close() {
    if (closing.current) return;
    closing.current = true;
    if (motion.current?.playState === "running") {
      motion.current.reverse(); backdrop.current?.reverse(); motion.current.onfinish = finish; return;
    }
    const el = img.current, to = figure.id === request.figure.id ? visible(request.origin?.querySelector('img') ?? request.origin) : null;
    if (!el?.animate) { finish(); return; }
    motion.current?.cancel(); backdrop.current?.cancel();
    backdrop.current = dialog.current?.animate?.([{ opacity: 1 }, { opacity: 0 }], { duration: reduced() ? 100 : 220, pseudoElement: "::backdrop", fill: "both" }) ?? null;
    motion.current = el.animate(reduced() || !to || natural ? [{ opacity: 1 }, { opacity: 0 }] : [{ transform: "none" }, { transform: delta(to, el.getBoundingClientRect()) }], { duration: reduced() ? 100 : 220, easing: "cubic-bezier(.4,0,1,1)", fill: "both" });
    motion.current.onfinish = finish;
  }
  function navigate(direction: number) {
    if (closing.current) return;
    const next = figures[figures.findIndex(f => f.id === figure.id) + direction];
    if (next) { motion.current?.cancel(); setFigure(next); setNatural(false); }
  }
  return <dialog ref={dialog} className="reader-image-dialog" aria-label="图片放大" onCancel={e => { e.preventDefault(); close(); }} onClick={e => { if (e.target === dialog.current) close(); }} onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); navigate(e.key === "ArrowLeft" ? -1 : 1); } }}>
    <header><strong>{figure.label}</strong><button onClick={() => navigate(-1)} disabled={figures[0]?.id === figure.id}>上一张</button><button onClick={() => navigate(1)} disabled={figures.at(-1)?.id === figure.id}>下一张</button><button aria-pressed={natural} onClick={() => setNatural(!natural)}>{natural ? "适应窗口" : "原尺寸查看"}</button><button onClick={close}>关闭放大</button></header>
    <div className="reader-image-viewport" data-natural={natural}><img ref={img} src={withAssetInstance(figure.src, instanceId)} alt={figure.caption || figure.label} /></div>
    {figure.caption && <div className="reader-image-caption"><MarkdownContent text={figure.caption} sourceId={figure.sourceId} /></div>}
  </dialog>;
}
