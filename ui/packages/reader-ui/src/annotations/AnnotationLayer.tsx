import { useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import { placeFloat } from "./placement";
export function AnnotationLayer({ stream, getRect, bubble = false, label, children }: {
  stream: RefObject<HTMLElement | null>; getRect: () => DOMRect; bubble?: boolean; label: string; children: ReactNode;
}) {
  const el = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const place = () => { if (el.current && stream.current) placeFloat(el.current, getRect(), stream.current, bubble ? "above" : "below", bubble ? "center" : "start"); };
    place(); window.addEventListener("resize", place); window.addEventListener("scroll", place, true);
    document.addEventListener("transitionend", place, true); document.addEventListener("animationend", place, true);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(place) : null;
    if (stream.current) observer?.observe(stream.current);
    const frame = requestAnimationFrame(place);
    return () => { cancelAnimationFrame(frame); observer?.disconnect(); window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); document.removeEventListener("transitionend", place, true); document.removeEventListener("animationend", place, true); };
  }, [stream, getRect, bubble, children]);
  return <div className="reader-anno-layer" data-anno-ui="" style={{ position: "absolute", inset: "0 auto auto 0", width: "100%", pointerEvents: "none", zIndex: 50 }}>
    <div ref={el} className={`reader-anno-float ${bubble ? "" : "reader-anno-pop"}`} style={{ pointerEvents: "auto", ...(bubble ? { background: "var(--reader-anno-bubble)", borderRadius: 10 } : {}) }} role={bubble ? undefined : "dialog"} aria-label={bubble ? undefined : label}>{children}</div>
  </div>;
}
