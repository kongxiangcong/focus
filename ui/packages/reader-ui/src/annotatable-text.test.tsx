import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MarkdownContent } from "./MarkdownContent";
import { markdownTree } from "./markdown-pipeline";
import { blockOf, domAnnotatableText, domOffset, hastAnnotatableText } from "./annotatable-text";
import { chunkFigures } from "./figures";
import type { ReaderChunk } from "@focus/reader-contracts";

afterEach(cleanup);
it.each([
  "普通中文 English 😀。\n\n第二段。",
  "1. 第一项\n2. **第二项**\n\n- 无序一\n- 无序二",
  "| 列一 | 列二 |\n| --- | --- |\n| 文字 | $x_i$ |",
  "公式前 $x_i$ 公式后。\n\n$$\nx^2\n$$\n\n末段。",
  "`code` 与 [链接](https://example.com) 和 **粗体** ==作者高亮==。\n\n```js\nconst a = 1;\n```",
  "<figure><img src=\"one.png\"><figcaption>排除图注</figcaption></figure>\n\n![图像](two.png) 正文。",
  String.raw`<table><tr><td>公式前 \(x_i\) 公式后</td><td>$y$</td></tr></table>`,
])("keeps DOM and HAST annotation offsets identical: %s", text => {
  const { container } = render(<MarkdownContent text={text} />);
  const root = container.querySelector(".focus-markdown")!;
  expect(domAnnotatableText(root).text).toBe(hastAnnotatableText(markdownTree(text)));
});

it("excludes math, figure captions and generated UI while retaining the surrounding text", () => {
  const { container } = render(<MarkdownContent text={'甲 $x$ 乙\n\n<figure><figcaption>图注</figcaption></figure>\n\n丙😀'} />);
  const root = container.querySelector(".focus-markdown")!;
  const ui = document.createElement("button"); ui.dataset.annoUi = ""; ui.textContent = "查看备注"; root.append(ui);
  expect(domAnnotatableText(root).text.replace(/\s/g, "")).toBe("甲乙丙😀");
});

it("excludes the generated figure control from the annotation text contract", () => {
  const text = "正文\n\n![Figure 1](images/one.png)\n\n后文";
  const chunk: ReaderChunk = { sourceId: "demo", planId: "p", chunkId: "c", index: 1, total: 1, sectionPath: [], sourceLines: [1, 2], sourceMarkdown: text, translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" };
  const { container } = render(<MarkdownContent text={text} sourceId="demo" figures={chunkFigures(chunk)} onFigure={vi.fn()} />);
  expect(container.querySelector(".reader-figure-link")).not.toBeNull();
  expect(domAnnotatableText(container.querySelector(".focus-markdown")!).text).toBe(hastAnnotatableText(markdownTree(text)));
});

it("maps text, element and excluded formula boundaries without crossing the chunk root", () => {
  const { container } = render(<MarkdownContent text={"甲**粗体**乙 $x$ 丙\n\n第二段"} />);
  const root = container.querySelector(".focus-markdown")!, p = root.querySelector("p")!;
  const strongText = p.querySelector("strong")!.firstChild!;
  expect(domOffset(root, strongText, 1, "start")).toBe(2);
  expect(domOffset(root, p, 1, "start")).toBe(1);
  const formula = p.querySelector(".katex")!;
  const beforeFormula = domAnnotatableText(p).text.indexOf(" 丙");
  expect(domOffset(root, formula.querySelector("annotation")!.firstChild!, 1, "start")).toBe(beforeFormula);
  expect(domOffset(root, formula.querySelector("annotation")!.firstChild!, 1, "end")).toBe(beforeFormula);
  expect(domOffset(root, document.body, 0, "start")).toBeNull();
  expect(blockOf(root, strongText)).toBe(p);
  expect(blockOf(root, document.body)).toBeNull();
});
