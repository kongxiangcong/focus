import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReaderChunk } from "@focus/reader-contracts";
import { ReadingChunk } from "./ReadingChunk";

afterEach(cleanup);
const chunk: ReaderChunk = { sourceId: "demo", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 2,
  sectionPath: ["Method"], sourceLines: [1, 3], sourceMarkdown: "Foreign original", translation: null,
  images: [], relevantGlossary: [], presentationStatus: "translation-required" };
it("does not flash foreign source while preparation is incomplete", () => {
  render(<ReadingChunk chunk={chunk} onReference={vi.fn()} />);
  expect(screen.queryByText("Foreign original")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("尚未准备完成");
});
it("displays Chinese source directly without a duplicated translation", () => {
  render(<ReadingChunk chunk={{ ...chunk, sourceMarkdown: "中文正文", presentationStatus: "source-ready" }} onReference={vi.fn()} />);
  expect(screen.getByText("中文正文")).toBeVisible();
  expect(screen.queryByRole("button", { name: "查看原文" })).not.toBeInTheDocument();
});
it("defaults to cached translation and reveals the original only on request", () => {
  render(<ReadingChunk chunk={{ ...chunk, translation: "缓存译文", presentationStatus: "presented" }} onReference={vi.fn()} />);
  expect(screen.getByText("缓存译文")).toBeVisible();
  expect(screen.queryByText("Foreign original")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看原文" }));
  expect(screen.getByText("Foreign original")).toBeVisible();
});
