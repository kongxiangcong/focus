import { useLayoutEffect, useRef, useState } from "react";

export function navigationBounds(container: number, min: number, max: number, mainMin: number) {
  return { min, max: Math.max(min, Math.min(max, container - mainMin)) };
}
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

/** Session-local width; the shell retains ownership of collapsed/mobile layout. */
export function NavigationResize({ enabled }: { enabled: boolean }) {
  const handle = useRef<HTMLDivElement>(null);
  const [preferred, setPreferred] = useState<number | null>(null);
  const [geometry, setGeometry] = useState({ min: 240, max: 420, initial: 288, step: 16, narrow: false });
  const drag = useRef<{ id: number; x: number; width: number; preferred: number | null; active: boolean } | null>(null);
  const width = clamp(preferred ?? geometry.initial, geometry.min, geometry.max);
  const visible = enabled && !geometry.narrow;
  function finish(cancel: boolean) {
    const pending = drag.current;
    if (!pending) return;
    drag.current = null;
    if (cancel) setPreferred(pending.preferred);
    const node = handle.current;
    node?.parentElement?.removeAttribute("data-nav-resizing");
    if (node?.hasPointerCapture(pending.id)) node.releasePointerCapture(pending.id);
  }
  useLayoutEffect(() => {
    const root = handle.current?.parentElement;
    if (!root) return;
    const measure = () => {
      const css = getComputedStyle(root);
      const value = (name: string, fallback: number) => parseFloat(css.getPropertyValue(name)) || fallback;
      const min = value("--reader-nav-min", 240), max = value("--reader-nav-max", 420);
      const initial = value("--reader-nav", 288), step = value("--reader-nav-step", 16);
      finish(true);
      setGeometry({ ...navigationBounds(root.clientWidth, min, max, value("--reader-main-min", 480)), initial, step,
        narrow: window.innerWidth <= 760 || root.clientWidth < min + value("--reader-main-min", 480) });
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(root); window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); finish(false); root.style.removeProperty("--nav-expanded-width"); };
  }, []);
  useLayoutEffect(() => { handle.current?.parentElement?.style.setProperty("--nav-expanded-width", `${width}px`); }, [width]);
  useLayoutEffect(() => {
    if (!visible) {
      if (document.activeElement === handle.current) handle.current?.parentElement?.querySelector<HTMLButtonElement>(".workspace-nav-toggle")?.focus();
      finish(true);
    }
  }, [visible]);
  return <div ref={handle} className="workspace-nav-resizer" hidden={!visible} tabIndex={visible ? 0 : -1}
    role="separator" aria-label="调整工作台导航宽度" aria-orientation="vertical" aria-controls="workspace-navigation"
    aria-valuemin={Math.round(geometry.min)} aria-valuemax={Math.round(geometry.max)} aria-valuenow={Math.round(width)}
    aria-valuetext={`${Math.round(width)} 像素；方向键调整，Home/End 到边界，Enter 恢复默认宽度`}
    title="拖动调整导航宽度；双击或 Enter 恢复默认宽度"
    onDoubleClick={() => setPreferred(null)}
    onKeyDown={event => {
      if (event.key === "Escape" && drag.current) { event.preventDefault(); event.stopPropagation(); finish(true); return; }
      const next = event.key === "ArrowLeft" ? width - geometry.step : event.key === "ArrowRight" ? width + geometry.step
        : event.key === "Home" ? geometry.min : event.key === "End" ? geometry.max : event.key === "Enter" ? geometry.initial : null;
      if (next !== null) { event.preventDefault(); finish(false); setPreferred(clamp(next, geometry.min, geometry.max)); }
    }}
    onPointerDown={event => {
      if (event.button !== 0 || !event.isPrimary || drag.current) return;
      event.preventDefault(); event.currentTarget.focus({ preventScroll: true });
      drag.current = { id: event.pointerId, x: event.clientX, width, preferred, active: false };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={event => {
      const pending = drag.current;
      if (!pending || pending.id !== event.pointerId) return;
      const delta = event.clientX - pending.x;
      if (!pending.active && Math.abs(delta) < 3) return;
      pending.active = true;
      event.currentTarget.parentElement?.setAttribute("data-nav-resizing", "true");
      setPreferred(clamp(pending.width + delta, geometry.min, geometry.max));
    }}
    onPointerUp={event => { if (drag.current?.id === event.pointerId) finish(false); }}
    onPointerCancel={event => { if (drag.current?.id === event.pointerId) finish(true); }}
    onLostPointerCapture={() => finish(true)} />;
}
