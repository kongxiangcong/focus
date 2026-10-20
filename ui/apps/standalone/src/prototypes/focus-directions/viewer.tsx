import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { FigureRef } from "./data";

export type ViewerRequest = { figure: FigureRef; origin: HTMLElement | null };

function delta(from: DOMRect, to: DOMRect) {
  return `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})`;
}
function visible(el: HTMLElement | null) {
  if (!el || !el.isConnected) return null;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.bottom > 0 && r.top < innerHeight ? r : null;
}

export function FigureViewer({ request, list, k, reduced, onClose }: {
  request: ViewerRequest; list: FigureRef[]; k: number; reduced: boolean; onClose: () => void;
}) {
  const [figure, setFigure] = useState(request.figure);
  const [actual, setActual] = useState(false);
  const img = useRef<HTMLImageElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const motion = useRef<Animation[]>([]);
  const closing = useRef(false);
  const origin = figure.id === request.figure.id ? request.origin : null;

  useLayoutEffect(() => {
    const el = img.current, bg = backdrop.current; if (!el || !bg) return;
    const from = visible(request.origin);
    const timing = { duration: (reduced ? 120 : 300) * k, easing: "cubic-bezier(.22,.8,.24,1)", fill: "both" as const };
    const to = el.getBoundingClientRect();
    motion.current = [
      bg.animate([{ opacity: 0 }, { opacity: 1 }], { ...timing, duration: 200 * k }),
      el.animate(reduced || !from ? [{ opacity: 0 }, { opacity: 1 }] : [{ transform: delta(from, to), borderRadius: "8px" }, { transform: "none", borderRadius: "4px" }], timing),
    ];
    closeButton.current?.focus({ preventScroll: true });
  }, []);

  function close() {
    if (closing.current) return;
    closing.current = true;
    const running = motion.current.filter(a => a.playState === "running");
    const finish = () => { onClose(); (origin ?? request.origin)?.focus?.({ preventScroll: true }); };
    if (running.length) {
      // Interrupted mid-open: play the same motion backwards from the current frame.
      running.forEach(a => a.reverse());
      running[running.length - 1].onfinish = finish;
      return;
    }
    const el = img.current, bg = backdrop.current; if (!el || !bg) { finish(); return; }
    const to = visible(origin), from = el.getBoundingClientRect();
    const timing = { duration: (reduced ? 100 : 220) * k, easing: "cubic-bezier(.4,0,.6,1)", fill: "both" as const };
    bg.animate([{ opacity: 1 }, { opacity: 0 }], timing);
    const a = el.animate(reduced || !to || actual ? [{ opacity: 1 }, { opacity: 0 }] : [{ transform: "none" }, { transform: delta(to, from) }], timing);
    a.onfinish = finish;
  }

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      const at = list.findIndex(f => f.id === figure.id);
      if (e.key === "ArrowRight" && at < list.length - 1) setFigure(list[at + 1]);
      if (e.key === "ArrowLeft" && at > 0) setFigure(list[at - 1]);
    };
    document.addEventListener("keydown", key, true);
    return () => document.removeEventListener("keydown", key, true);
  });

  const at = list.findIndex(f => f.id === figure.id);
  return <div className="fd-viewer" role="dialog" aria-modal="true" aria-label={figure.label}>
    <div className="fd-viewer-bg" ref={backdrop} onClick={close} />
    <div className="fd-viewer-bar">
      <strong>{figure.label}</strong><span className="fd-viewer-count">{at + 1} / {list.length}</span>
      <span className="fd-grow" />
      <button disabled={at <= 0} onClick={() => setFigure(list[at - 1])} aria-label="上一张">‹</button>
      <button disabled={at >= list.length - 1} onClick={() => setFigure(list[at + 1])} aria-label="下一张">›</button>
      <button onClick={() => setActual(v => !v)}>{actual ? "适应窗口" : "原尺寸"}</button>
      <button ref={closeButton} onClick={close}>关闭 <kbd>Esc</kbd></button>
    </div>
    <div className={`fd-viewer-stage${actual ? " is-actual" : ""}`} onClick={e => { if (e.target === e.currentTarget) close(); }}>
      <img ref={img} key={figure.id} src={figure.src} alt={figure.caption} className={figure.id === request.figure.id ? undefined : "fd-viewer-swap"} />
    </div>
    <p className="fd-viewer-caption">{figure.caption}</p>
  </div>;
}