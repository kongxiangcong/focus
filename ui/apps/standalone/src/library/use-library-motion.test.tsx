// @vitest-environment jsdom
import { useRef } from "react";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { LibrarySource } from "@focus/reader-contracts";
import { reducedLibraryMotion, useLibraryMotion } from "./use-library-motion";
const sources = ["a", "b", "c"].map(sourceId => ({ sourceId } as LibrarySource));
function Harness({ rows, all = rows, context = "topic" }: { rows: LibrarySource[]; all?: LibrarySource[]; context?: string }) {
  const ref = useRef<HTMLDivElement>(null); useLibraryMotion(ref, rows, all, false, context, true);
  return <div ref={ref} className="library-sources">{rows.map(source => <div data-source-id={source.sourceId} key={source.sourceId} />)}</div>;
}
const animate = vi.fn(function (this: HTMLElement, _frames: Keyframe[], _options: KeyframeAnimationOptions) { const node = this; return { cancel: vi.fn(() => { node.style.transform = "none"; }), onfinish: null }; });
beforeEach(() => {
  document.documentElement.dataset.reducedMotion = "false";
  document.documentElement.style.setProperty("--reader-duration-travel", "380ms"); document.documentElement.style.setProperty("--reader-duration-move", "240ms"); document.documentElement.style.setProperty("--reader-gap-sm", "8px"); document.documentElement.style.setProperty("--reader-ease-inout", "linear"); document.documentElement.style.setProperty("--reader-ease-out", "linear");
  animate.mockClear(); vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) { return { top: Array.from(this.parentElement?.children ?? []).indexOf(this) * 100 - (this.closest<HTMLElement>(".library-sources")?.scrollTop ?? 0) } as DOMRect; });
  Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete (HTMLElement.prototype as Partial<HTMLElement>).animate; document.documentElement.removeAttribute("data-reduced-motion"); document.documentElement.removeAttribute("style"); });
it("animates only reordering with unchanged context and membership, retargeting from the in-flight position", () => {
  const app = render(<Harness rows={sources.slice(0, 2)} />); expect(animate).not.toHaveBeenCalled();
  app.rerender(<Harness rows={[sources[1], sources[0]]} />); expect(animate).toHaveBeenCalledTimes(2);
  const node = app.container.querySelector<HTMLElement>('[data-source-id="a"]')!; node.style.transform = "matrix(1,0,0,1,0,-40)";
  app.rerender(<Harness rows={sources.slice(0, 2)} />); expect(animate.mock.calls[2][0]).toEqual([{ transform: "translateY(60px)" }, { transform: "none" }]);
  animate.mockClear(); app.rerender(<Harness rows={[sources[1], sources[0]]} context="search" />); expect(animate).not.toHaveBeenCalled();
  app.rerender(<Harness rows={[sources[0]]} all={sources.slice(0, 2)} context="search" />); expect(animate).not.toHaveBeenCalled();
});
it("animates a newly registered source once, never initial data or filter/view remounts", () => {
  const app = render(<Harness rows={sources.slice(0, 2)} />); expect(animate).not.toHaveBeenCalled();
  app.rerender(<Harness rows={sources} />); expect(animate).toHaveBeenCalledTimes(1); expect(animate.mock.calls[0][0]).toEqual([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }]);
  animate.mockClear(); app.rerender(<Harness rows={sources.slice(0, 2)} all={sources} context="filter" />); app.rerender(<Harness rows={sources} context="topic" />); expect(animate).not.toHaveBeenCalled();
});
it("honors either reduced-motion preference and cancels active motion when the setting changes", async () => {
  const app = render(<Harness rows={sources.slice(0, 2)} />); app.rerender(<Harness rows={[sources[1], sources[0]]} />); const active = animate.mock.results.map(result => result.value);
  await act(async () => { document.documentElement.dataset.reducedMotion = "true"; }); active.forEach(animation => expect(animation.cancel).toHaveBeenCalled());
  animate.mockClear(); app.rerender(<Harness rows={sources.slice(0, 2)} />); expect(animate).not.toHaveBeenCalled(); expect(reducedLibraryMotion()).toBe(true);
  document.documentElement.dataset.reducedMotion = "false"; vi.stubGlobal("matchMedia", () => ({ matches: true })); expect(reducedLibraryMotion()).toBe(true); app.rerender(<Harness rows={[sources[1], sources[0]]} />); expect(animate).not.toHaveBeenCalled();
});

it("uses scroll-content coordinates when an ordering change follows scrolling", () => {
  const app = render(<Harness rows={sources.slice(0, 2)} />); app.container.querySelector<HTMLElement>(".library-sources")!.scrollTop = 240;
  app.rerender(<Harness rows={[sources[1], sources[0]]} />);
  expect(animate.mock.calls.map(call => call[0][0].transform)).toEqual(["translateY(100px)", "translateY(-100px)"]);
});
