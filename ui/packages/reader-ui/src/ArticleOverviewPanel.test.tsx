import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type ArticleOverview, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { ArticleOverviewPanel } from "./ArticleOverviewPanel";

afterEach(cleanup);
const ready: ArticleOverview = { sourceId: "paper", title: "测试论文", status: "ready", revision: "v1", guide: "原来计算需要等待数据。作者先分析原因，再设计搬运方法，最后以模型分析检验效果。",
  structure: [{ id: "root", parentId: null, title: "问题与方法", description: "先找出原因，再提出方法。", sourceLines: [1, 4] }], chunkNodes: ["root"] };
const host = (initial: ArticleOverview): ReaderHost => ({ getReadingWindow: vi.fn(), continueReading: vi.fn(), sendMessage: vi.fn(),
  getArticleOverview: vi.fn(async () => readerSuccess(initial)), prepareArticleOverview: vi.fn(async () => readerSuccess(ready)) });
it("previews title, Chinese tree and guide in order without reading actions", async () => {
  const api = host(ready);
  const { container } = render(<ArticleOverviewPanel host={api} sourceId="paper" title="测试论文" />);
  await screen.findByRole("heading", { name: "文章导读" });
  expect(container.querySelector("h1")!.compareDocumentPosition(screen.getByText("问题与方法")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByText("问题与方法").compareDocumentPosition(screen.getByRole("heading", { name: "文章导读" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByText("进入正文")).not.toBeInTheDocument();
  expect(api.continueReading).not.toHaveBeenCalled();
  expect(api.prepareArticleOverview).not.toHaveBeenCalled();
});
it("prepares a missing overview and retries errors with a stable request identity", async () => {
  const api = host({ ...ready, status: "missing", guide: undefined, structure: undefined });
  vi.mocked(api.prepareArticleOverview!).mockResolvedValueOnce({ ok: false, error: { code: "unavailable", message: "暂时断线", retryable: true } });
  render(<ArticleOverviewPanel host={api} sourceId="paper" title="测试论文" />);
  fireEvent.click(await screen.findByRole("button", { name: "准备文章结构" }));
  await screen.findByRole("alert");
  const first = vi.mocked(api.prepareArticleOverview!).mock.calls[0][1];
  fireEvent.click(screen.getByRole("button", { name: "准备文章结构" }));
  await screen.findByRole("heading", { name: "文章导读" });
  expect(vi.mocked(api.prepareArticleOverview!).mock.calls[1][1]).toBe(first);
  expect(api.continueReading).not.toHaveBeenCalled();
});
it("running tasks cannot be submitted again", async () => {
  const api = host({ ...ready, status: "running" });
  render(<ArticleOverviewPanel host={api} sourceId="paper" title="测试论文" />);
  await screen.findByText("正在准备中文骨架与导读…");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("formal intro uses the same content and enters the body only on click", async () => {
  const api=host(ready), enter=vi.fn();
  const view: ReadingWindow = { status: "empty", source: { sourceId: "paper", title: "测试论文", topicId: null }, current: null, history: [], conversation: [], structureIntro: true, readingStarted: false, articleOverview: ready };
  render(<ArticleOverviewPanel host={api} sourceId="paper" title="测试论文" view={view} onBody={enter} />);
  await screen.findByText(ready.guide!);
  expect(enter).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "进入正文" }));
  expect(enter).toHaveBeenCalledTimes(1);
});
it("discard a late response when switching to another source", async () => {
  let resolve!: (result: ReturnType<typeof readerSuccess<ArticleOverview>>) => void;
  const api=host(ready);
  vi.mocked(api.getArticleOverview!).mockImplementationOnce(() => new Promise(r => { resolve=r; }));
  const rendered=render(<ArticleOverviewPanel host={api} sourceId="old" title="旧文章" />);
  rendered.rerender(<ArticleOverviewPanel host={api} sourceId="paper" title="测试论文" />);
  await screen.findByText(ready.guide!);
  resolve(readerSuccess({ ...ready, sourceId: "old", title: "旧文章" }));
  await waitFor(() => expect(screen.queryByText("旧文章")).not.toBeInTheDocument());
});
