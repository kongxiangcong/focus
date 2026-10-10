import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReaderAgentState } from "@focus/reader-contracts";
import { TaskProgress } from "./TaskProgress";

afterEach(() => { cleanup(); vi.useRealTimers(); });
function run(): NonNullable<ReaderAgentState["run"]> {
  return { runId: "r1", status: "running", error: null, approvals: [], activity: [],
    progress: { label: "解析材料", startedAt: 100000, updatedAt: 100000 } };
}
it("shows observed progress, elapsed time and quiet periods without inventing a percentage", () => {
  vi.useFakeTimers(); vi.setSystemTime(100000);
  const value = run(); const app = render(<TaskProgress run={value} />);
  expect(screen.getByRole("status")).toHaveTextContent("解析材料");
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("value");
  act(() => { vi.advanceTimersByTime(16000); });
  expect(screen.getByText(/暂未收到新进展/)).toBeInTheDocument();
  app.rerender(<TaskProgress run={{ ...value, progress: { ...value.progress!, label: "规划阅读", updatedAt: 116000 } }} />);
  expect(screen.queryByText(/暂未收到新进展/)).not.toBeInTheDocument();
  app.rerender(<TaskProgress run={{ ...value, status: "completed", progress: { ...value.progress!, finishedAt: 116000 } }} />);
  act(() => { vi.advanceTimersByTime(5000); });
  expect(screen.getByLabelText("已用时间")).toHaveTextContent("16 秒");
  expect(screen.getByRole("status")).toHaveTextContent("已完成");
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});
it("prioritizes approval and failure over stale stages and hides raw tool details", () => {
  const value = { ...run(), activity: [{ id: "a", title: "commandExecution", status: "inProgress", detail: "private command" }] };
  const app = render(<TaskProgress run={{ ...value, status: "approval" }} />);
  expect(screen.getByRole("status")).toHaveTextContent("等待你的操作");
  expect(screen.queryByText(/暂未收到新进展|private command/)).not.toBeInTheDocument();
  app.rerender(<TaskProgress run={{ ...value, status: "failed" }} />);
  expect(screen.getByRole("status")).toHaveTextContent("处理失败");
});

it("shows pre-answer summarization and stage-specific elapsed time", () => {
  vi.useFakeTimers(); vi.setSystemTime(200000);
  const value = { ...run(), progress: { label: "整理历史对话", startedAt: 190000,
    stageStartedAt: 195000, updatedAt: 195000 },
    phaseTiming: { sentAt: 190000, summaryStart: 195000, summaryBatches: 1, summaryInputChars: 9400 } };
  const app = render(<TaskProgress run={value} />);
  expect(screen.getByRole("status")).toHaveTextContent("整理历史对话");
  expect(screen.getByLabelText("当前阶段耗时")).toHaveTextContent("5 秒");
  act(() => vi.advanceTimersByTime(17000));
  expect(screen.getByText(/主回答尚未提交/)).toBeInTheDocument();
  app.rerender(<TaskProgress run={{ ...value, progress: { ...value.progress,
    label: "等待回复", stageStartedAt: 218000, updatedAt: 218000 } }} />);
  expect(screen.getByRole("status")).toHaveTextContent("等待回复");
  expect(screen.queryByText(/主回答尚未提交/)).not.toBeInTheDocument();
});
