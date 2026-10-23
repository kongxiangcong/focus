import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FixtureReaderHost } from "../../../../apps/standalone/src/adapters/fixture-reader-host";
import type { ReaderChunk, ReadingWindow } from "@focus/reader-contracts";
import { FoldedChunkNotes } from "./FoldedChunkNotes";
const chunk: ReaderChunk = { sourceId: "demo-paper", planId: "p1", chunkId: "c1", index: 1, total: 1, sectionPath: ["Method"], sourceLines: [1, 4],
  sourceMarkdown: "Example.", translation: null, images: [], relevantGlossary: [], bundleVersion: "fixture-bundle-v1", presentationStatus: "source-ready" };
beforeEach(() => sessionStorage.clear()); afterEach(cleanup);
it("creates and edits paragraph notes inside the fold without AI and keeps the saved fold expanded", async () => {
  const host = new FixtureReaderHost({ source: { sourceId: chunk.sourceId, title: "Demo", topicId: null }, chunks: [chunk] });
  const initial = await host.getReadingWindow(); if (!initial.ok) throw Error("fixture unavailable");
  const create = vi.spyOn(host, "createSourceNote"), send = vi.spyOn(host, "sendMessage");
  function Harness() {
    const [view, setView] = useState<ReadingWindow>(initial.ok ? initial.value : null!);
    return <FoldedChunkNotes chunk={chunk} notes={view.sourceNotes ?? []} host={host} onAccept={setView} />;
  }
  render(<Harness />); fireEvent.click(screen.getByRole("button", { name: /记小段笔记/ }));
  const input = screen.getByRole("textbox"); fireEvent.change(input, { target: { value: "段落想法" } });
  fireEvent.keyDown(input, { key: "Enter" });
  const toggle = await screen.findByRole("button", { name: /小段笔记 · 1/ }); expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ content: "段落想法", kind: "thought", origin: "user", chunk: { planId: "p1", chunkId: "c1" } }));
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "修改想法" } }); fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
  await screen.findByText("修改想法"); await waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument());
});
