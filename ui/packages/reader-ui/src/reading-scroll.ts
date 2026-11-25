import { useLayoutEffect, useRef, useState, type RefObject } from "react";

export const startLine = (pane: HTMLElement) => Math.max(24, pane.clientHeight * .1);
export const tailSpace = (height: number, line: number, group: number, keep: number, reserve = 0) =>
  Math.max(128, height - line - group, keep, reserve);
export const scrollDuration = (distance: number) => Math.min(520, Math.max(280, 200 + Math.abs(distance) * .12));
export const easeOutQuart = (t: number) => 1 - (1 - t) ** 4;

/** Offset chains share a document origin, including when pane is not an offset parent. */
export function layoutTop(pane: HTMLElement, element: HTMLElement) {
  const offset = (el: HTMLElement) => {
    let top = 0;
    for (let node: HTMLElement | null = el; node; node = node.offsetParent as HTMLElement | null) top += node.offsetTop;
    return top;
  };
  return offset(element) - offset(pane) - pane.clientTop;
}

export class ReadingScroll {
  private isStreaming = false;
  private animation: number | null = null;
  private tick: number | null = null;
  private resizeObserver?: ResizeObserver;
  private mutationObserver?: MutationObserver;
  private anchor: { el: HTMLElement; offset: number } | null = null;
  private geometry = "";
  private reserved = { px: 0, until: 0 };
  private heldUntil = 0;
  private positionVersion = 0;
  private returnTo: number | null = null;
  private lastScroll = 0;
  private latestDismissed = false;
  private backDismissed = false;
  private notice = { latest: false, back: false };
  private emit = (latest: boolean, back: boolean) => {
    this.notice = { latest, back };
    this.notify(latest && !this.latestDismissed && !this.atLatest(), back && !this.backDismissed);
  };
  dismissLatest = () => { this.latestDismissed = true; this.emit(this.notice.latest, this.notice.back); };
  dismissBack = () => { this.backDismissed = true; this.emit(this.notice.latest, this.notice.back); };
  constructor(readonly pane: HTMLElement, readonly end: HTMLElement, readonly spacer: HTMLElement,
    readonly follow: { current: boolean }, private notify: (latest: boolean, back: boolean) => void) {}

  get streaming() { return this.isStreaming; }
  get programmaticPositionVersion() { return this.positionVersion; }
  set streaming(value: boolean) {
    if (this.isStreaming === value) return;
    this.isStreaming = value;
    this.schedule();
  }

  cancel = () => { if (this.animation !== null) cancelAnimationFrame(this.animation); this.animation = null; };
  private streamingOutput = () => this.streaming
    ? Array.from(this.pane.querySelectorAll<HTMLElement>('[data-streaming="true"]')).find(el => !el.closest('[hidden]'))
    : undefined;
  latestBottom = () => {
    const output = this.streamingOutput();
    return output ? layoutTop(this.pane, output) + output.offsetHeight : layoutTop(this.pane, this.end);
  };
  atLatest = () => this.latestBottom() - this.pane.scrollTop - this.pane.clientHeight <= 48;
  contentChanged = () => {
    if (!this.follow.current) this.emit(true, this.returnTo !== null);
    this.schedule();
  };
  sizeSpacer = () => {
    const last = this.pane.querySelectorAll<HTMLElement>('[data-reading-group]');
    const bottom = layoutTop(this.pane, this.end);
    const group = last.length ? bottom - layoutTop(this.pane, last[last.length - 1]) : 0;
    const floor = performance.now() < this.reserved.until ? this.reserved.px : 0;
    this.spacer.style.height = `${tailSpace(this.pane.clientHeight, startLine(this.pane), group,
      this.pane.scrollTop + this.pane.clientHeight - bottom, floor)}px`;
  };
  capture = () => {
    const line = this.pane.scrollTop + startLine(this.pane);
    const el = Array.from(this.pane.querySelectorAll<HTMLElement>('.focus-reading .focus-markdown > *'))
      .find(el => layoutTop(this.pane, el) + el.offsetHeight > line);
    this.anchor = el ? { el, offset: layoutTop(this.pane, el) - this.pane.scrollTop } : null;
  };
  restore = () => {
    if (this.anchor?.el.isConnected) this.writePosition(layoutTop(this.pane, this.anchor.el) - this.anchor.offset);
  };
  hold = (extra = 0) => {
    this.positionVersion += 1;
    this.cancel(); this.capture(); this.heldUntil = performance.now() + 700;
    this.reserved = { px: this.spacer.offsetHeight + extra, until: this.heldUntil };
    this.sizeSpacer();
    this.schedule();
  };
  holdDisclosure = (button: HTMLElement) => {
    this.hold();
    // The disclosure remains visible even when the entire answer below it disappears.
    this.anchor = { el: button, offset: Math.max(startLine(this.pane),
      Math.min(this.pane.clientHeight - button.offsetHeight, layoutTop(this.pane, button) - this.pane.scrollTop)) };
  };
  animateTo = (raw: number, done?: () => void) => {
    this.positionVersion += 1;
    this.cancel(); this.sizeSpacer();
    const top = Math.max(0, Math.min(raw, this.pane.scrollHeight - this.pane.clientHeight));
    const from = this.pane.scrollTop, distance = top - from;
    if (document.documentElement.dataset.reducedMotion === 'true' || globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches || Math.abs(distance) < 2) {
      this.writePosition(top); this.capture(); done?.(); return;
    }
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / scrollDuration(distance));
      this.writePosition(from + distance * easeOutQuart(t));
      this.capture();
      if (t < 1) this.animation = requestAnimationFrame(step);
      else { this.animation = null; done?.(); }
    };
    this.animation = requestAnimationFrame(step);
  };
  land = (el: HTMLElement) => {
    this.latestDismissed = false; this.backDismissed = false;
    this.heldUntil = 0; this.returnTo = null; this.follow.current = true; this.emit(false, false);
    this.animateTo(layoutTop(this.pane, el) - startLine(this.pane));
  };
  jump = (el: HTMLElement) => {
    this.backDismissed = false;
    this.heldUntil = 0; this.returnTo = this.pane.scrollTop; this.follow.current = false;
    this.emit(false, true); this.animateTo(layoutTop(this.pane, el) - startLine(this.pane) - 40);
  };
  goBack = () => {
    if (this.returnTo === null) return;
    const top = this.returnTo; this.returnTo = null; this.emit(false, false); this.animateTo(top);
  };
  toLatest = () => {
    this.latestDismissed = false; this.backDismissed = false;
    this.heldUntil = 0; this.returnTo = null; this.follow.current = true; this.emit(false, false);
    this.animateTo(this.latestBottom() - this.pane.clientHeight + 24);
  };
  reveal = (el: HTMLElement) => {
    const top = layoutTop(this.pane, el);
    if (top > this.pane.scrollTop + this.pane.clientHeight * .6) this.animateTo(top - this.pane.clientHeight * .45);
  };
  userIntent = (up: boolean) => {
    this.cancel(); this.heldUntil = 0;
    if (up) { this.latestDismissed = false; this.follow.current = false; this.emit(true, this.returnTo !== null); }
    this.lastScroll = this.pane.scrollTop;
  };
  onScroll = () => {
    if (performance.now() < this.heldUntil) return;
    if (this.animation === null && !this.atLatest()) {
      this.follow.current = false;
      if (this.streaming) this.emit(true, this.returnTo !== null);
    }
    // An upward gesture near the bottom must not re-enable follow via its own scroll event.
    if (this.animation === null && this.pane.scrollTop > this.lastScroll && this.atLatest()) {
      this.follow.current = true; this.emit(false, this.returnTo !== null);
    }
    this.lastScroll = this.pane.scrollTop;
    this.capture();
    this.schedule();
  };
  private sample = () => {
    this.tick = null;
    const holding = performance.now() < this.heldUntil;
    const anchorTop = this.anchor?.el.isConnected ? layoutTop(this.pane, this.anchor.el) : "";
    const geometry = `${this.pane.clientWidth}:${this.pane.clientHeight}:${layoutTop(this.pane, this.end)}:${anchorTop}`;
    this.sizeSpacer();
    if (this.animation === null && (geometry !== this.geometry || holding)) this.restore();
    this.geometry = geometry;
    const output = !holding && this.animation === null && this.follow.current ? this.streamingOutput() : undefined;
    if (output) {
      const top = layoutTop(this.pane, output) + output.offsetHeight - this.pane.clientHeight + 24;
      if (top > this.pane.scrollTop) this.writePosition(top);
    }
    if (holding) this.schedule();
    else this.capture();
  };
  private writePosition = (top: number) => {
    const previous = this.pane.scrollTop;
    this.pane.scrollTop = top;
    if (this.pane.scrollTop !== previous) this.positionVersion += 1;
  };
  private schedule = () => {
    if (this.tick === null) this.tick = requestAnimationFrame(this.sample);
  };
  start = () => {
    this.capture();
    const content = this.pane.querySelector(".focus-content") ?? this.pane;
    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(this.schedule);
      this.resizeObserver.observe(this.pane);
      if (content !== this.pane) this.resizeObserver.observe(content);
    }
    this.mutationObserver = new MutationObserver(records => {
      if (records.some(record => record.target !== this.spacer)) this.schedule();
    });
    this.mutationObserver.observe(content, {
      subtree: true, childList: true, characterData: true, attributes: true,
      attributeFilter: ["class", "style", "hidden", "open", "data-streaming"],
    });
    this.schedule();
  };
  dispose = () => {
    this.cancel();
    if (this.tick !== null) cancelAnimationFrame(this.tick);
    this.tick = null;
    this.resizeObserver?.disconnect();
    this.mutationObserver?.disconnect();
  };
}

export function useReadingScroll(pane: RefObject<HTMLElement | null>, follow: RefObject<boolean>, scope: string, streaming: boolean, enabled: boolean) {
  const end = useRef<HTMLDivElement>(null), spacer = useRef<HTMLDivElement>(null);
  const controller = useRef<ReadingScroll | null>(null);
  const [state, setState] = useState({ latest: false, back: false });
  useLayoutEffect(() => {
    setState({ latest: false, back: false });
    if (!pane.current || !end.current || !spacer.current || !enabled) { controller.current = null; return; }
    const scroll = new ReadingScroll(pane.current, end.current, spacer.current, follow,
      // Navigation also changes the follow ref. Publish even when notice flags stay false
      // so consumers observe the settled frontier before the next review gesture.
      (latest, back) => setState({ latest, back }));
    controller.current = scroll; setState({ latest: false, back: false }); scroll.start();
    return () => { scroll.dispose(); controller.current = null; };
  }, [scope, enabled]);
  useLayoutEffect(() => {
    const control = controller.current;
    if (!control) return;
    if (streaming && !control.streaming && !control.atLatest()) {
      follow.current = false; control.contentChanged();
    }
    control.streaming = streaming;
  });
  return { controller, end, spacer, ...state };
}
