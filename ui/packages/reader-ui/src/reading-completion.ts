import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import { startLine, type ReadingScroll } from "./reading-scroll";

const edgeTolerance = 1;
const scrollInputTimeout = 220;

function measure(pane: HTMLElement, body: HTMLElement, controller: ReadingScroll) {
  if (!pane.clientHeight || body.closest("[hidden], [inert]")) return null;
  const bounds = body.getBoundingClientRect();
  if (!bounds.height) return null;
  const group = body.closest("[data-reading-group]");
  const top = pane.getBoundingClientRect().top + pane.clientTop;
  return {
    top: bounds.top - top,
    bottom: bounds.bottom - top,
    height: pane.clientHeight,
    width: pane.clientWidth,
    scrollTop: pane.scrollTop,
    requiresScroll: !!group && bounds.bottom - group.getBoundingClientRect().top + startLine(pane) > pane.clientHeight + edgeTolerance,
    version: controller.programmaticPositionVersion,
  };
}

type Position = NonNullable<ReturnType<typeof measure>>;

export function useReadingCompletion(
  pane: RefObject<HTMLElement | null>, controller: RefObject<ReadingScroll | null>,
  scope: string | undefined, fullscreen: boolean, paused: boolean, finish: () => void,
) {
  const body = useRef<HTMLDivElement>(null);
  const intent = useRef<{ before: Position; expires: number } | null>(null);
  const touchY = useRef<number | null>(null);
  const [inlineScope, setInlineScope] = useState<string>();

  const position = () => scope && pane.current && body.current && controller.current
    ? measure(pane.current, body.current, controller.current)
    : null;
  const refreshInline = (current = position()) => {
    const fullyVisible = current && current.top >= -edgeTolerance && current.bottom <= current.height + edgeTolerance;
    setInlineScope(fullyVisible ? scope : undefined);
  };
  const cancelIntent = () => { intent.current = null; };

  useLayoutEffect(() => {
    cancelIntent();
    touchY.current = null;
    refreshInline();
    const stream = pane.current;
    const text = body.current;
    if (!scope || !stream || !text) return;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => refreshInline());
    observer?.observe(stream);
    observer?.observe(text);
    const content = stream.querySelector(".focus-content");
    if (content) observer?.observe(content);
    // A passive gesture can move the compositor before its DOM handler. Read
    // the starting position synchronously only while the final body is active.
    stream.addEventListener("wheel", onWheel, { passive: false });
    stream.addEventListener("touchstart", onTouchStart, { passive: false });
    stream.addEventListener("touchmove", onTouchMove, { passive: false });
    stream.addEventListener("touchcancel", cancelIntent);
    window.addEventListener("pointerdown", cancelIntent, true);
    window.addEventListener("blur", cancelIntent);
    document.addEventListener("visibilitychange", cancelIntent);
    return () => {
      observer?.disconnect();
      stream.removeEventListener("wheel", onWheel);
      stream.removeEventListener("touchstart", onTouchStart);
      stream.removeEventListener("touchmove", onTouchMove);
      stream.removeEventListener("touchcancel", cancelIntent);
      window.removeEventListener("pointerdown", cancelIntent, true);
      window.removeEventListener("blur", cancelIntent);
      document.removeEventListener("visibilitychange", cancelIntent);
    };
  }, [scope, fullscreen, paused]);

  function scrollIntent(down: boolean) {
    const before = down && !paused && document.visibilityState === "visible" ? position() : null;
    intent.current = before ? { before, expires: performance.now() + scrollInputTimeout } : null;
  }

  function onScroll() {
    if (!scope) return;
    const after = position();
    refreshInline(after);
    const armed = intent.current;
    cancelIntent();
    if (!armed || !after || paused || document.visibilityState !== "visible" || performance.now() > armed.expires) return;
    const { before } = armed;
    const moved = after.scrollTop - before.scrollTop;
    if (moved <= 0 || before.version !== after.version || before.width !== after.width || before.height !== after.height ||
        Math.abs(before.top - after.top - moved) > edgeTolerance ||
        Math.abs(before.bottom - after.bottom - moved) > edgeTolerance) return;
    const reachedEnd = before.requiresScroll && before.bottom > before.height + edgeTolerance &&
      after.bottom <= after.height + edgeTolerance && after.bottom >= 0;
    if (reachedEnd) finish();
    else if (after.bottom > after.height + edgeTolerance) {
      // Native key scrolling and touch momentum can dispatch several scroll events.
      intent.current = { before: after, expires: performance.now() + scrollInputTimeout };
    }
  }

  function onWheel(event: WheelEvent) {
    if (!event.isTrusted || event.defaultPrevented || event.ctrlKey || event.shiftKey || !readingTarget(event)) return;
    scrollIntent(event.deltaY > 0 && event.deltaY >= Math.abs(event.deltaX));
  }

  function onTouchStart(event: TouchEvent) {
    touchY.current = event.isTrusted && event.touches.length === 1 && readingTarget(event) ? event.touches[0].clientY : null;
    cancelIntent();
  }

  function onTouchMove(event: TouchEvent) {
    const previous = touchY.current;
    if (previous === null) return;
    if (event.defaultPrevented || !event.isTrusted || event.touches.length !== 1) {
      touchY.current = null;
      cancelIntent();
      return;
    }
    const next = event.touches[0].clientY;
    touchY.current = next;
    if (previous !== next) scrollIntent(next < previous);
  }

  return { body, inline: !!scope && inlineScope === scope, scrollIntent, onScroll, cancelIntent };
}

function readingTarget(event: Event) {
  return event.target instanceof Element && !event.target.closest(".reader-anno-rail, .reader-chunk-notes-fold");
}
