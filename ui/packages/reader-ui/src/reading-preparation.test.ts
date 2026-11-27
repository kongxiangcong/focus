import { expect, it } from "vitest";
import type { ReadingPreparation } from "@focus/reader-contracts";
import { preparationText } from "./reading-preparation";

it("shows the active translation batch and its saved progress independently of chunk counts", () => {
  const preparation: ReadingPreparation = {
    source_id: "paper", status: "running", step: "document", total: 23, completed: 0,
    ready: false, error: null, plan_id: "plan-001",
    document_batch: { index: 2, total: 4, completed: 1, source_lines: [25, 32],
      action: "retry", retry_count: 1, message: "译文缺少图片链接", last_progress_at: "2026-11-25T08:00:00Z" },
  };
  const status = preparationText(preparation);
  expect(status).toContain("校验重试 1/2 · 第 2/4 批（原文第 25–32 行） · 已保存 1 批");
  expect(status).toContain("译文缺少图片链接");
  expect(preparationText({ ...preparation, status: "interrupted" })).toContain("准备已中断 · 第 2/4 批");
});
