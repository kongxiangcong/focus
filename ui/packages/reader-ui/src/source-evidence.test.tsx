import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { projectEvidence } from "./source-evidence";
import { MarkdownContent } from "./MarkdownContent";
import { citedMarkdown, messageEvidence } from "./source-evidence";

const document: ReadingDocument = { sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nAn alias keeps order.\n\nAn alias keeps order.\n\n| Value |\n| --- |\n| 42 |", lineCount: 9 };
const evidence: ValidatedAnswerEvidence = { evidenceId: "a".repeat(24), sourceId: "paper", bundleVersion: "v1", messageId: "answer", discussionId: "discussion", answerRevision: "rev", displayNumber: 1, sourceLines: [5, 5], quote: { exact: "alias keeps order", prefix: "", suffix: "" }, relation: "supports" };
describe("source evidence rendering boundary", () => {
  it("uses source lines to disambiguate identical visible sentences", () => {
    const result = projectEvidence(document, [evidence]);
    expect(result[0].kind).toBe("exact");
    const { container } = render(<MarkdownContent text={document.markdown} sourceEvidence={{ document, evidence: [evidence] }} />);
    expect(container.querySelectorAll("mark.source-evidence")).toHaveLength(1);
    expect(container.querySelectorAll("p")[0].querySelector("mark")).toBeNull();
    expect(container.querySelectorAll("p")[1].querySelector("mark")?.textContent).toBe("alias keeps order");
    expect(screen.getByRole("button", { name: "返回回答证据 1" })).toBeTruthy();
  });
  it("does not silently resolve ambiguous, outdated or fabricated quotes", () => {
    expect(projectEvidence(document, [{ ...evidence, sourceLines: [1, 9] }])[0].kind).toBe("unavailable");
    expect(projectEvidence(document, [{ ...evidence, bundleVersion: "v0" }])[0].kind).toBe("unavailable");
    expect(projectEvidence(document, [{ ...evidence, sourceId: "other" }])[0].kind).toBe("unavailable");
  });
  it("locates table cells and preserves sanitization", () => {
    const table = { ...evidence, sourceLines: [9, 9] as const, quote: { exact: "42", prefix: "", suffix: "" } };
    expect(projectEvidence(document, [table])[0].kind).toBe("exact");
    const hostile = { ...document, markdown: '<script>alert(1)</script>\n\nSafe text' };
    const { container } = render(<MarkdownContent text={hostile.markdown} sourceEvidence={{ document: hostile, evidence: [] }} />);
    expect(container.querySelector("script")).toBeNull();
  });
  it("uses block targets for new verified quotations", () => {
    const doc = { ...document, markdown: "# Paper\n\n**An alias** keeps order.\n\nThe next paragraph.", lineCount: 5 };
    const ref = { ...evidence, renderGranularity: "block" as const, sourceLines: [3, 5] as const,
      quote: { exact: "**An alias** keeps order.\n\nThe next", prefix: "", suffix: "" } };
    expect(projectEvidence(doc, [ref])[0].kind).toBe("block");
    expect(projectEvidence(doc, [{ ...ref, quote: { ...ref.quote, exact: "missing quote" } }])[0].kind).toBe("unavailable");
    const { container } = render(<MarkdownContent text={doc.markdown} sourceEvidence={{ document: doc,
      evidence: [{ ...ref, sourceLines: [3, 3], quote: { ...ref.quote, exact: "keeps order" } }] }} />);
    expect(container.querySelectorAll("p[data-evidence-block]")).toHaveLength(1);
    expect(container.querySelector("mark.source-evidence")).toBeNull();
  });
  it("binds original images to the displayed source version", () => {
    const doc = { ...document, markdown: "![Figure](images/image-001.png)" };
    const { container } = render(<MarkdownContent text={doc.markdown} sourceId="paper" sourceEvidence={{ document: doc, evidence: [] }} />);
    expect(container.querySelector("img")?.getAttribute("src")).toBe("/reader/assets/paper/images/image-001.png?bundle=v1");
  });
  it("only turns revision and discussion bound markers into buttons", () => {
    const message = { messageId: "answer", chunkId: "", role: "assistant" as const, content: `Claim [[e:${evidence.evidenceId}]]`, answerRevision: "rev", evidence: [evidence] };
    expect(messageEvidence(message, document, "discussion")).toHaveLength(1);
    expect(messageEvidence(message, document, "other")).toHaveLength(0);
    expect(messageEvidence({ ...message, answerRevision: "edited" }, document, "discussion")).toHaveLength(0);
    expect(citedMarkdown(message, [])).not.toContain("#e-");
  });
  it("keeps the focused citation button mounted across hover callback updates", () => {
    const text = `[1](#e-${evidence.evidenceId})`;
    const { container, rerender } = render(<MarkdownContent text={text} onCitation={() => {}} onCitationHover={() => {}} />);
    const button = container.querySelector("button")!;
    button.focus();
    rerender(<MarkdownContent text={text} onCitation={() => {}} onCitationHover={() => {}} />);
    expect(container.querySelector("button")).toBe(button);
    expect(button.ownerDocument.activeElement).toBe(button);
  });
  it("keeps permanent annotation offsets intact when evidence numbers are inserted", () => {
    const projection = projectEvidence(document, [evidence])[0];
    const { container } = render(<MarkdownContent text={document.markdown}
      sourceEvidence={{ document, evidence: [evidence] }} marks={projection.kind === "exact" ? [{ key: "permanent", start: projection.start, end: projection.end, highlightId: "saved", ariaLabel: "重点" }] : []} />);
    expect(container.querySelector("mark.source-evidence .reader-anno--hl")).not.toBeNull();
    expect([...container.querySelectorAll("[data-anno-key=permanent]")].map(e => e.textContent).join("")).toBe("alias keeps order");
  });
  it("maps lines back after TeX normalization inserts display-math lines", () => {
    const doc = { ...document, markdown: "# Formula\n\n\\[x^2\\]\n\nThe same result.\n\nThe same result.", lineCount: 7 };
    const ref = { ...evidence, sourceLines: [7, 7] as const, quote: { exact: "The same result.", prefix: "", suffix: "" } };
    expect(projectEvidence(doc, [ref])[0].kind).toBe("exact");
    const { container } = render(<MarkdownContent text={doc.markdown} sourceEvidence={{ document: doc, evidence: [ref] }} />);
    const paragraphs = [...container.querySelectorAll("p")].filter(p => p.textContent?.includes("The same result."));
    expect(paragraphs[0].querySelector("mark")).toBeNull();
    expect(paragraphs[1].querySelector("mark")?.textContent).toBe("The same result.");
  });
  it("resolves a late citation in a long source without choosing an earlier duplicate", () => {
    const paragraph = "The repeated result is constrained to this experiment. ".repeat(8);
    const markdown = Array.from({ length: 400 }, () => paragraph).join("\n\n");
    const doc = { ...document, markdown, lineCount: 799 };
    const ref = { ...evidence, sourceLines: [799, 799] as const, quote: { exact: paragraph.trimEnd(), prefix: "", suffix: "" } };
    const started = performance.now();
    const result = projectEvidence(doc, [ref])[0];
    console.info(`Source evidence: ${markdown.length} characters, 400 paragraphs, ${(performance.now() - started).toFixed(1)} ms`);
    expect(result.kind).toBe("exact");
    if (result.kind !== "exact") throw new Error("Expected an exact projection");
    expect(result.start).toBeGreaterThan(markdown.length * .95);
  });
});
