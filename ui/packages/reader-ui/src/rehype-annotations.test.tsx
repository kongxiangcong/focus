import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { MarkdownContent } from "./MarkdownContent";
import { domAnnotatableText } from "./annotatable-text";
import type { RenderMark } from "./rehype-annotations";

afterEach(cleanup);
const mark: RenderMark = { key: "n:one", start: 1, end: 6, highlightId: "h1", noteId: "n1", ariaLabel: "备注：文字", fresh: ["hl", "note"] };
it("marks across inline formatting, keeps the surrogate-pair tail intact and focuses only its first fragment", () => {
  const { container } = render(<MarkdownContent text={"**甲乙**丙丁😀"} marks={[mark]} />);
  const root = container.querySelector(".focus-markdown")!;
  expect(root.querySelectorAll('[data-anno-key="n:one"][tabindex="0"]')).toHaveLength(1);
  expect(root.querySelector("strong .reader-anno")?.textContent).toBe("乙");
  expect(root.querySelector(".reader-anno--tail")?.textContent).toBe("😀");
  expect(root.querySelector(".reader-anno--tail")?.classList.contains("reader-anno--hl")).toBe(true);
  expect(root.querySelector(".reader-anno-bulb")?.getAttribute("aria-label")).toBe("查看备注");
  expect(root.querySelector(".reader-anno-bulb")?.classList.contains("is-new")).toBe(true);
  expect(domAnnotatableText(root).text).toBe("甲乙丙丁😀");
});

it("excludes formulas from markers and retains the original text after injecting pending or note UI", () => {
  const { container } = render(<MarkdownContent text={"甲 $x$ 乙"} marks={[{ ...mark, start: 0, end: 4, pending: true }]} />);
  const root = container.querySelector(".focus-markdown")!;
  expect(root.querySelector(".katex")?.closest(".reader-anno")).toBeNull();
  expect(root.querySelector(".reader-anno--pending")).not.toBeNull();
  expect(domAnnotatableText(root).text).toBe("甲  乙");
});

it("does not produce a bulb for highlights and preserves an unmarked document verbatim", () => {
  const a = render(<MarkdownContent text="只有重点" />).container.innerHTML;
  cleanup();
  const b = render(<MarkdownContent text="只有重点" marks={[]} />).container.innerHTML;
  expect(b).toBe(a);
  cleanup();
  const { container } = render(<MarkdownContent text="只有重点" marks={[{ key: "h:h1", start: 0, end: 4, highlightId: "h1", ariaLabel: "重点" }]} />);
  expect(container.querySelector(".reader-anno-bulb")).toBeNull();
  expect(domAnnotatableText(container.querySelector(".focus-markdown")!).text).toBe("只有重点");
});
