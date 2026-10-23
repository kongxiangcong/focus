import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FixtureReaderHost } from "../../../../apps/standalone/src/adapters/fixture-reader-host";
import { FocusReader } from "../FocusReader";
import { readerSuccess, type ReaderChunk, type ReaderHost } from "@focus/reader-contracts";
import { domAnnotatableText } from "../annotatable-text";

const chunk: ReaderChunk = { sourceId: "demo-paper", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 1,
  sectionPath: ["Method"], sourceLines: [1, 4], sourceMarkdown: "First sentence. Second sentence.\n\nAnother paragraph.",
  translation: null, images: [], relevantGlossary: [], bundleVersion: "fixture-bundle-v1", presentationStatus: "source-ready" };
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  HTMLElement.prototype.scrollIntoView = vi.fn(); HTMLElement.prototype.scrollTo = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  Range.prototype.getBoundingClientRect = () => new DOMRect(100, 120, 140, 20);
  Range.prototype.getClientRects = () => ({ 0: new DOMRect(100, 120, 140, 20), length: 1, item: () => null, [Symbol.iterator]: function* () { yield this[0]; } }) as DOMRectList;
});
afterEach(() => { cleanup(); window.getSelection()?.removeAllRanges(); });
async function setup(configure?: (host: ReaderHost) => void) {
  const host = new FixtureReaderHost({ source: { sourceId: chunk.sourceId, title: "Demo", topicId: null }, chunks: [chunk] });
  configure?.(host);
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByText(/First sentence/);
  return host;
}
function selectText(start = 0, end = 15, cross = false) {
  const paragraphs = document.querySelectorAll(".focus-reading .focus-markdown p");
  const nodes = domAnnotatableText(paragraphs[0]).nodes;
  const first = nodes.find(item => start >= item.start && start < item.start + item.node.length)!;
  const last = [...nodes].reverse().find(item => end > item.start && end <= item.start + item.node.length)!;
  const range = document.createRange(); range.setStart(first.node, start - first.start);
  range.setEnd(cross ? paragraphs[1].firstChild! : last.node, cross ? 7 : end - last.start);
  window.getSelection()!.removeAllRanges(); window.getSelection()!.addRange(range);
  fireEvent.pointerUp(paragraphs[0]);
  fireEvent.mouseUp(paragraphs[0]);
}
it("offers highlight, note, and reference for an in-block selection and persists emphasis", async () => {
  const host = await setup(); const create = vi.spyOn(host, "createHighlight");
  selectText();
  fireEvent.click(await screen.findByRole("button", { name: "重点" }));
  await waitFor(() => expect(document.querySelector(".reader-anno--hl")).toBeInTheDocument());
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ layer: "source", range: { start: 0, end: 15 },
    quote: expect.objectContaining({ exact: "First sentence." }), chunk: { planId: "plan-001", chunkId: "chunk-001" } }));
});
it("keeps cross-block selections available only for reference questions", async () => {
  await setup(); selectText(0, 15, true);
  const toolbar = await screen.findByRole("toolbar", { name: "选区操作" });
  expect(within(toolbar).getByRole("button", { name: "引用提问" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重点" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "备注" })).not.toBeInTheDocument();
});
it("saves a sentence note in-place, opens the bulb, edits, and deletes with undo", async () => {
  const host = await setup(); const create = vi.spyOn(host, "createSourceNote"), change = vi.spyOn(host, "changeSourceNote");
  selectText(); fireEvent.click(await screen.findByRole("button", { name: "备注" }));
  const input = screen.getByRole("textbox", { name: "备注文字" });
  fireEvent.change(input, { target: { value: "自己的想法" } }); fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑备注" })).not.toBeInTheDocument());
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ kind: "thought", origin: "user", content: "自己的想法",
    sentence: expect.objectContaining({ range: { start: 0, end: 15 }, quote: expect.objectContaining({ exact: "First sentence." }) }) }));
  const bulb = screen.getByRole("button", { name: "查看备注" }); fireEvent.click(bulb);
  const popup = screen.getByRole("dialog", { name: "备注" }); expect(within(popup).getByText("自己的想法")).toBeInTheDocument();
  fireEvent.keyDown(popup, { key: "Escape" }); expect(bulb).toHaveFocus();
  fireEvent.click(bulb); fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注文字" }), { target: { value: "修改后的备注" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(change).toHaveBeenCalledWith(chunk.sourceId, expect.any(String), "edit", 1, expect.any(String), "修改后的备注"));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑备注" })).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "查看备注" })); fireEvent.click(within(screen.getByRole("dialog", { name: "备注" })).getByRole("button", { name: "删除标注" }));
  await screen.findByText("已删除标注"); expect(screen.queryByRole("button", { name: "查看备注" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "撤销" }));
  await screen.findByRole("button", { name: "查看备注" });
});
it("keeps nonempty editor drafts through outside selection and attachment toggles, and restores discarded drafts", async () => {
  await setup(); selectText(); fireEvent.click(await screen.findByRole("button", { name: "备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注文字" }), { target: { value: "保留草稿" } });
  fireEvent.pointerDown(screen.getByText(/Another paragraph/)); selectText(16, 22);
  expect(screen.getByRole("textbox", { name: "备注文字" })).toHaveValue("保留草稿");
  fireEvent.click(document.querySelector(".reader-attach-toggle")!);
  expect(screen.getByRole("textbox", { name: "备注文字" })).toHaveValue("保留草稿");
  fireEvent.keyDown(screen.getByRole("textbox", { name: "备注文字" }), { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "编辑备注" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "撤销" }));
  expect(screen.getByRole("textbox", { name: "备注文字" })).toHaveValue("保留草稿");
});
it("restores a sentence draft after remount and clears empty outside editors", async () => {
  const host = await setup(); selectText(); fireEvent.click(await screen.findByRole("button", { name: "备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注文字" }), { target: { value: "刷新后恢复" } });
  cleanup(); window.getSelection()?.removeAllRanges(); render(<FocusReader host={host} appearance="mist" />);
  await screen.findByText(/First sentence/); selectText(); fireEvent.click(await screen.findByRole("button", { name: "备注" }));
  expect(screen.getByRole("textbox", { name: "备注文字" })).toHaveValue("刷新后恢复");
  fireEvent.change(screen.getByRole("textbox", { name: "备注文字" }), { target: { value: "" } });
  fireEvent.pointerDown(screen.getByText(/Another paragraph/));
  expect(screen.queryByRole("dialog", { name: "编辑备注" })).not.toBeInTheDocument();
});
it("retains failed note input and retries the same request once; bundle changes offer no retry", async () => {
  const host = await setup(); const save = vi.spyOn(host, "createSourceNote"); host.failNext("note");
  selectText(); fireEvent.click(await screen.findByRole("button", { name: "备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注文字" }), { target: { value: "失败也不丢" } });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "备注文字" }), { key: "Enter" });
  await screen.findByText("备注未保存"); expect(screen.getByRole("textbox", { name: "备注文字" })).toHaveValue("失败也不丢");
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑备注" })).not.toBeInTheDocument());
  expect(save.mock.calls[0][0].requestId).toBe(save.mock.calls[1][0].requestId);
  expect((await host.getReadingWindow()).ok && document.querySelectorAll("[data-anno-bulb]").length).toBe(1);
  host.writeOutcome = "bundle_changed";
  selectText(16, 31); fireEvent.click(await screen.findByRole("button", { name: "重点" }));
  await screen.findByText("这段原文已更新，标注未保存"); expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
});
it("rejects partial overlap and opens existing annotations when selection is contained", async () => {
  await setup(); selectText(); fireEvent.click(await screen.findByRole("button", { name: "重点" }));
  await waitFor(() => expect(document.querySelector(".reader-anno--hl")).toBeInTheDocument());
  selectText(5, 20); await screen.findByText("与已有标注重叠，请缩小选区");
  expect(screen.queryByRole("button", { name: "备注" })).not.toBeInTheDocument();
  selectText(2, 10); const toolbar = await screen.findByRole("toolbar", { name: "标注操作" });
  expect(within(toolbar).getByRole("button", { name: "取消重点" })).toHaveAttribute("aria-pressed", "true");
});
it("respects optional Host annotation capabilities and preserves selected reference text", async () => {
  const host = await setup(host => { host.createHighlight = undefined; host.createSourceNote = undefined; });
  const send = vi.spyOn(host, "sendMessage"); selectText();
  const toolbar = await screen.findByRole("toolbar", { name: "选区操作" });
  expect(within(toolbar).queryAllByRole("button")).toHaveLength(1);
  fireEvent.click(within(toolbar).getByRole("button", { name: "引用提问" }));
  fireEvent.change(screen.getByRole("textbox", { name: "输入问题或阅读需求" }), { target: { value: "请解释" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(send).toHaveBeenCalledWith(expect.objectContaining({ content: "> First sentence.\n\n请解释", receipt: expect.objectContaining({ chunkId: chunk.chunkId }) })));
});
it("uses the selected occurrence's visible layer when a Chunk appears twice", async () => {
  const translated = { ...chunk, translation: "译文句子。还有一句。" };
  const host = new FixtureReaderHost({ source: { sourceId: chunk.sourceId, title: "Demo", topicId: null }, chunks: [translated] });
  const result = await host.getReadingWindow(); if (!result.ok) throw Error("fixture unavailable");
  const view = { ...result.value, timeline: [{ kind: "reading" as const, eventId: "first", chunk: translated }, { kind: "reading" as const, eventId: "last", chunk: translated }] };
  vi.spyOn(host, "getReadingWindow").mockResolvedValue(readerSuccess(view)); const save = vi.spyOn(host, "createHighlight");
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findAllByText("译文句子。还有一句。");
  fireEvent.click(screen.getAllByRole("button", { name: "查看原文" })[0]);
  selectText(); fireEvent.click(await screen.findByRole("button", { name: "重点" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ layer: "source", quote: expect.objectContaining({ exact: "First sentence." }) })));
});
it("keeps typing during a save and applies the next save as an edit of the acknowledged note", async () => {
  const host = await setup(), original = host.createSourceNote.bind(host);
  let release: (() => void) | undefined;
  const create = vi.spyOn(host, "createSourceNote").mockImplementationOnce(async input => {
    const result = await original(input); await new Promise<void>(resolve => { release = resolve; }); return result;
  });
  const edit = vi.spyOn(host, "changeSourceNote");
  selectText(); fireEvent.click(await screen.findByRole("button", { name: "备注" }));
  const field = screen.getByRole("textbox", { name: "备注文字" });
  fireEvent.change(field, { target: { value: "第一份备注" } }); fireEvent.keyDown(field, { key: "Enter" });
  fireEvent.change(field, { target: { value: "写入期间继续修改" } });
  await waitFor(() => expect(release).toBeDefined()); await act(async () => release!());
  expect(field).toHaveValue("写入期间继续修改");
  await waitFor(() => expect(screen.getByRole("button", { name: "保存" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(edit).toHaveBeenCalledWith(chunk.sourceId, expect.any(String), "edit", 1, expect.any(String), "写入期间继续修改"));
  expect(create).toHaveBeenCalledOnce();
});
