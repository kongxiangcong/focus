import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MarkdownContent } from "./MarkdownContent";
import { ReadingChunk } from "./ReadingChunk";
import { chunkFigures } from "./figures";
import type { ReaderChunk } from "@focus/reader-contracts";

afterEach(cleanup);
const formula = String.raw`M0_i \rightarrow S_i \rightarrow M1_i`;
it.each([
  [`$${formula}$`, false],
  [`$$\n${formula}\n$$`, true],
  [String.raw`\(${formula}\)`, false],
  [String.raw`\[${formula}\]`, true],
  [`[ ${formula} ]`, true],
  [formula, true],
  [String.raw`\[
${formula}
\]`, true],
])("renders supported formula notation: %s", (text, display) => {
  const { container } = render(<MarkdownContent text={text} />);
  expect(container.querySelectorAll(".katex")).toHaveLength(1);
  expect(container.querySelector("annotation")).toHaveTextContent(formula);
  expect(container.querySelectorAll(".msupsub")).toHaveLength(3);
  expect(container.querySelector(".katex-error")).toBeNull();
  expect(!!container.querySelector(".katex-display")).toBe(display);
});

it("renders inline brackets and TeX delimiters alongside Chinese prose and GFM tables", () => {
  const text = String.raw`流程为 [ ${formula} ] 并保持原文。

行内为 \(x_i^2\)。

| 阶段 | 依赖 |
| --- | --- |
| S | \(x_i\) |`;
  const { container } = render(<MarkdownContent text={text} />);
  expect(container).toHaveTextContent("流程为");
  expect(container).toHaveTextContent("并保持原文。");
  expect(container.querySelectorAll(".katex")).toHaveLength(3);
  expect(screen.getByRole("table").querySelector(".katex")).not.toBeNull();
});

it("leaves code, links, ordinary brackets and prose literal", () => {
  const text = `\`${formula}\`\n\n\`\`\`tex\n[ ${formula} ]\n\`\`\`\n\n[${formula}](https://example.com)\n\n[普通说明]\n\nUse \\rightarrow to denote a dependency.`;
  const { container } = render(<MarkdownContent text={text} />);
  expect(container.querySelector(".katex")).toBeNull();
  expect(container.querySelector("pre code")).toHaveTextContent(`[ ${formula} ]`);
  expect(screen.getByRole("link")).toHaveAttribute("href", "https://example.com");
  expect(container).toHaveTextContent("[普通说明]");
  expect(container).toHaveTextContent(String.raw`Use \rightarrow to denote a dependency.`);
});

it("renders TeX delimiters in raw parser table cells without allowing unsafe HTML", () => {
  const { container } = render(<MarkdownContent text={String.raw`<table><tr><td>\(${formula}\)</td></tr></table><script>alert(1)</script>`} />);
  expect(screen.getByRole("cell").querySelector(".katex")).not.toBeNull();
  expect(container.querySelector("script")).toBeNull();
});

it("keeps invalid math visible without crashing the reading flow", () => {
  const { container } = render(<MarkdownContent text={String.raw`\(\frac{a}{\)

后续正文`} />);
  expect(container.querySelector(".katex-error")).not.toBeNull();
  expect(screen.getByText("后续正文")).toBeVisible();
});

it("renders original and translated Reading Chunks while preserving figure links", () => {
  const chunk: ReaderChunk = { sourceId: "demo", planId: "p1", chunkId: "c1", index: 1, total: 1,
    sectionPath: ["Method"], sourceLines: [1, 5], sourceMarkdown: `[ ${formula} ]\n\n![Figure 1](images/one.png)`,
    translation: String.raw`译文公式 \(${formula}\)`, images: [], relevantGlossary: [], presentationStatus: "presented" };
  const { container } = render(<ReadingChunk chunk={chunk} onReference={vi.fn()} onFigure={vi.fn()} />);
  expect(container.querySelector("annotation")).toHaveTextContent(formula);
  expect(chunkFigures(chunk)).toHaveLength(1);
  expect(screen.getByRole("button", { name: "在资料栏固定" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看原文" }));
  expect(container.querySelectorAll(".katex")).toHaveLength(1);
  expect(container.querySelector("annotation")).toHaveTextContent(formula);
  expect(container.querySelector(".katex-display")).not.toBeNull();
  expect(screen.getByRole("button", { name: "在资料栏固定" })).toBeInTheDocument();
});

it("preserves adjacent dollar formulas and their surrounding prose", () => {
  const { container } = render(<MarkdownContent text={String.raw`先看 $x_i$ 再看 \(y_i\) 并保留正文。

[ ${formula} ]

最后 $z_i$。`} />);
  expect(container.querySelectorAll(".katex")).toHaveLength(4);
  expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
  expect(container).toHaveTextContent("并保留正文。");
});
