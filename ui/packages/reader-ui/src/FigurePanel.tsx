import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { MarkdownContent } from "./MarkdownContent";
import type { Figure } from "./figures";

export function FigurePanel({ figures, selected, selectionVersion, scope, onScope, onSelect }: {
  figures: readonly Figure[]; selected: string | null; scope: "chunk" | "all";
  selectionVersion: number;
  onScope: (scope: "chunk" | "all") => void; onSelect: (figure: Figure) => void;
}) {
  const scroll = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [zoom, setZoom] = useState<Figure | null>(null);
  const [natural, setNatural] = useState(false);
  const [failed, setFailed] = useState<string[]>([]);
  const locating = useRef(false);
  function locate() {
    const pane = scroll.current;
    const target = Array.from(pane?.querySelectorAll<HTMLElement>("[data-figure-id]") ?? []).find(el => el.dataset.figureId === selected);
    if (pane && target) pane.scrollTop += target.getBoundingClientRect().top - pane.getBoundingClientRect().top;
    else if (pane) pane.scrollTop = 0;
  }
  useLayoutEffect(() => {
    locating.current = !!selected;
    locate();
  }, [selected, scope, selectionVersion]);
  useEffect(() => {
    if (zoom) dialog.current?.showModal();
    else { dialog.current?.close(); if (opener.current?.isConnected) opener.current.focus({ preventScroll: true }); }
  }, [zoom]);
  return <>
    <div className="reader-figure-controls"><strong>{scope === "all" ? "全文图片" : "本段图片"} · {figures.length}</strong>
      {scope === "all" && <button onClick={() => onScope("chunk")}>返回本段图片</button>}
      <details className="reader-figure-navigation"><summary>图片导航</summary>
        <div role="group" aria-label="图片范围"><button aria-pressed={scope === "chunk"} onClick={() => onScope("chunk")}>本段图片</button><button aria-pressed={scope === "all"} onClick={() => onScope("all")}>全文图片</button></div>
        <nav aria-label="图片目录">{figures.map(f => <button key={f.id} title={f.caption || f.label} aria-current={selected === f.id ? "true" : undefined} onClick={() => onSelect(f)}>
          <img src={f.src} alt="" loading="lazy" /><span>{f.label} · {f.caption.slice(0, 70) || "无图注"}</span>
        </button>)}</nav>
      </details>
    </div>
    <div ref={scroll} className="reader-figure-scroll" tabIndex={0} aria-label="图片浏览" onWheel={() => { locating.current = false; }} onTouchStart={() => { locating.current = false; }} onPointerDown={() => { locating.current = false; }} onKeyDown={() => { locating.current = false; }}>
      {!figures.length && <p>{scope === "all" ? "来源尚无可用图片。" : "本段无图片。可在图片导航中选择全文图片。"}</p>}
      {figures.map(f => <figure key={f.id} data-figure-id={f.id} data-selected={selected === f.id}>
        <button className="reader-figure-zoom" aria-label={`放大${f.label}`} onClick={event => { opener.current = event.currentTarget; setNatural(false); setZoom(f); }}>
          <img src={f.src} alt={f.caption || f.label} loading="lazy" onLoad={() => { if (locating.current) locate(); }} onError={() => setFailed(old => old.includes(f.id) ? old : [...old, f.id])} />
        </button>
        {failed.includes(f.id) && <p role="status">图片加载失败。<a href={f.src} target="_blank" rel="noreferrer">打开原图</a></p>}
        <figcaption><small>{f.label}</small>{f.caption && <MarkdownContent text={f.caption} sourceId={f.sourceId} />}</figcaption>
      </figure>)}
    </div>
    <dialog ref={dialog} className="reader-image-dialog" aria-label="图片放大" onCancel={event => { event.preventDefault(); setZoom(null); }} onClick={event => { if (event.target === dialog.current) setZoom(null); }}>
      <header><strong>{zoom?.label}</strong><button aria-pressed={natural} onClick={() => setNatural(!natural)}>{natural ? "适应窗口" : "原尺寸查看"}</button><button onClick={() => setZoom(null)}>关闭放大</button></header>
      <div className="reader-image-viewport" data-natural={natural}>{zoom && <img src={zoom.src} alt={zoom.caption || zoom.label} />}</div>
      {zoom?.caption && <div className="reader-image-caption"><MarkdownContent text={zoom.caption} sourceId={zoom.sourceId} /></div>}
    </dialog>
  </>;
}
