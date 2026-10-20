import { useCallback, useEffect, useRef, useState } from "react";

const LATEST_SLACK = 48;
// Room for the composer to collapse at the very end without the browser clamping scrollTop.
const MIN_TAIL = 128;
const ease = (t: number) => 1 - Math.pow(1 - t, 4);

export function startLine(pane: HTMLElement) { return Math.max(24, Math.round(pane.clientHeight * 0.1)); }
function topWithin(pane: HTMLElement, el: Element) {
  return el.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
}
// Layout position, ignoring entrance transforms that are still running.
function layoutTop(pane: HTMLElement, el: Element) {
  let top = 0, node: HTMLElement | null = el as HTMLElement;
  while (node && node !== pane) { top += node.offsetTop; node = node.offsetParent as HTMLElement | null; }
  return node === pane ? top : topWithin(pane, el);
}

export function useReadingScroll({ k, reduced, streaming }: { k: number; reduced: boolean; streaming: boolean }) {
  const pane = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const spacer = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const frame = useRef<number | null>(null);
  const viewingLock = useRef(0);
  const reserved = useRef({ px: 0, until: 0 });
  const anchor = useRef<{ el: Element; offset: number } | null>(null);
  const pendingView = useRef<{ unit: number; timer: number } | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const viewingRef = useRef<number | null>(null);
  const setView = (unit: number | null) => { viewingRef.current = unit; setViewing(unit); };
  const [showLatest, setShowLatest] = useState(false);
  const [returnTo, setReturnTo] = useState<number | null>(null);
  const opts = useRef({ k, reduced, streaming }); opts.current = { k, reduced, streaming };

  const cancel = useCallback(() => { if (frame.current) cancelAnimationFrame(frame.current); frame.current = null; }, []);

  const endTop = () => (pane.current && end.current ? topWithin(pane.current, end.current) : 0);
  // The newest content is the streaming answer when there is one; in paragraph-grouped layouts it may sit mid-document.
  const latestBottom = () => {
    const p = pane.current; if (!p) return 0;
    const live = p.querySelector('[data-streaming="true"]');
    return live ? live.getBoundingClientRect().bottom - p.getBoundingClientRect().top + p.scrollTop : endTop();
  };
  const atLatest = () => { const p = pane.current; return !!p && latestBottom() - (p.scrollTop + p.clientHeight) <= LATEST_SLACK; };

  const sizeSpacer = useCallback(() => {
    const p = pane.current, s = spacer.current; if (!p || !s) return;
    const targets = p.querySelectorAll<HTMLElement>("[data-landing]");
    const last = targets[targets.length - 1];
    const tail = last ? endTop() - layoutTop(p, last) : 0;
    const keep = p.scrollTop + p.clientHeight - endTop();
    const floor = performance.now() < reserved.current.until ? reserved.current.px : 0;
    s.style.height = `${Math.max(MIN_TAIL, p.clientHeight - startLine(p) - tail, keep, floor)}px`;
  }, []);

  // Call before the viewport grows (composer collapse) so the browser never clamps scrollTop.
  const reserve = useCallback((px: number) => {
    const s = spacer.current; if (!s) return;
    reserved.current = { px: s.offsetHeight + px, until: performance.now() + 700 * opts.current.k };
    s.style.height = `${reserved.current.px}px`;
  }, []);

  const animateTo = useCallback((raw: number, done?: () => void) => {
    const p = pane.current; if (!p) return;
    cancel();
    const top = Math.max(0, Math.min(raw, p.scrollHeight - p.clientHeight));
    const from = p.scrollTop, distance = top - from;
    if (opts.current.reduced || Math.abs(distance) < 2) { p.scrollTop = top; done?.(); return; }
    const duration = Math.min(520, Math.max(280, 200 + Math.abs(distance) * 0.12)) * opts.current.k;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      p.scrollTop = from + distance * ease(t);
      if (t < 1) frame.current = requestAnimationFrame(step); else { frame.current = null; done?.(); }
    };
    frame.current = requestAnimationFrame(step);
  }, [cancel]);

  const commitViewing = useCallback(() => {
    const p = pane.current; if (!p || performance.now() < viewingLock.current) return;
    const line = p.scrollTop + p.clientHeight * 0.32;
    const blocks = Array.from(p.querySelectorAll<HTMLElement>("[data-unit]"));
    if (!blocks.length) { setView(null); return; }
    let candidate = blocks[0];
    for (const b of blocks) if (topWithin(p, b) <= line) candidate = b;
    const unit = Number(candidate.dataset.unit);
    const current = viewingRef.current;
    if (current === unit) { if (pendingView.current) { clearTimeout(pendingView.current.timer); pendingView.current = null; } return; }
    // Ignore boundary jitter: the reading line must clear the boundary by 24px and hold for 140ms.
    if (current !== null && unit > current && line - topWithin(p, candidate) < 24) return;
    if (pendingView.current?.unit === unit) return;
    if (pendingView.current) clearTimeout(pendingView.current.timer);
    pendingView.current = { unit, timer: window.setTimeout(() => { pendingView.current = null; setView(unit); }, 140) };
  }, []);

  const lockViewing = useCallback((unit: number, ms: number) => {
    viewingLock.current = performance.now() + ms;
    if (pendingView.current) { clearTimeout(pendingView.current.timer); pendingView.current = null; }
    setView(unit);
  }, []);

  const land = useCallback((el: Element | null, opts2?: { unit?: number; instant?: boolean }) => {
    const p = pane.current; if (!p || !el) return;
    sizeSpacer();
    setReturnTo(null);
    follow.current = true; setShowLatest(false);
    if (opts2?.unit) lockViewing(opts2.unit, 700 * opts.current.k);
    const top = layoutTop(p, el) - startLine(p);
    if (opts2?.instant) { cancel(); p.scrollTop = top; } else animateTo(top);
  }, [animateTo, cancel, lockViewing, sizeSpacer]);

  const jump = useCallback((el: Element | null, unit?: number) => {
    const p = pane.current; if (!p || !el) return;
    follow.current = false;
    setReturnTo(p.scrollTop);
    if (unit) lockViewing(unit, 700 * opts.current.k);
    animateTo(layoutTop(p, el) - startLine(p) - 40);
  }, [animateTo, lockViewing]);

  const goBack = useCallback(() => {
    if (returnTo === null) return;
    animateTo(returnTo, () => { commitViewing(); });
    setReturnTo(null);
  }, [animateTo, commitViewing, returnTo]);

  const toLatest = useCallback(() => {
    const p = pane.current; if (!p) return;
    follow.current = true; setShowLatest(false); setReturnTo(null);
    animateTo(latestBottom() - p.clientHeight + 24);
  }, [animateTo]);

  const pin = useCallback(() => {
    const p = pane.current; if (!p || !follow.current || frame.current || !opts.current.streaming) return;
    const target = latestBottom() - p.clientHeight + 24;
    if (target > p.scrollTop + 1) p.scrollTop = target;
  }, []);

  const reveal = useCallback((el: Element | null) => {
    const p = pane.current; if (!p || !el) return;
    follow.current = true; setShowLatest(false);
    const top = topWithin(p, el);
    if (top > p.scrollTop + p.clientHeight * 0.6) animateTo(top - p.clientHeight * 0.45);
  }, [animateTo]);

  const userIntent = useCallback((up: boolean) => {
    cancel();
    if (up) { follow.current = false; if (opts.current.streaming) setShowLatest(true); }
  }, [cancel]);

  const onScroll = useCallback(() => {
    if (!frame.current) {
      if (atLatest()) { follow.current = true; setShowLatest(false); }
      else if (!follow.current && opts.current.streaming) setShowLatest(true);
    }
    commitViewing();
  }, [commitViewing]);

  useEffect(() => {
    const p = pane.current, c = content.current; if (!p || !c || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => { sizeSpacer(); pin(); });
    observer.observe(p); observer.observe(c);
    return () => observer.disconnect();
  }, [pin, sizeSpacer]);

  useEffect(() => { if (!streaming && atLatest()) setShowLatest(false); }, [streaming]);

  // Hold the line being read across a layout change (columns reflow, threads move).
  const capture = useCallback(() => {
    const p = pane.current; if (!p) return;
    const top = p.getBoundingClientRect().top, line = top + startLine(p);
    const blocks = p.querySelectorAll("[data-source-text] .focus-markdown > *, .fd-q, .fd-a");
    for (const el of blocks) {
      const r = el.getBoundingClientRect();
      if (r.bottom > line) { anchor.current = { el, offset: r.top - top }; return; }
    }
    anchor.current = null;
  }, []);
  const restore = useCallback(() => {
    const p = pane.current, a = anchor.current; if (!p || !a || !a.el.isConnected) return;
    cancel();
    p.scrollTop += a.el.getBoundingClientRect().top - p.getBoundingClientRect().top - a.offset;
    anchor.current = null;
  }, [cancel]);

  return { pane, content, end, spacer, reserve, capture, restore, follow, viewing, showLatest, returnTo, land, jump, goBack, toLatest, reveal, userIntent, onScroll, sizeSpacer, commitViewing, cancel };
}