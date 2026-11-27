import type { ReadingPreparation } from "@focus/reader-contracts";

const steps: Record<string, string> = {
  context: "正在分析全文", plan: "正在生成计划", document: "正在翻译正文", translate: "正在翻译", check: "正在检查", repair: "正在修订译文",
};
const failures: Record<string, string> = {
  failed: "准备失败", interrupted: "准备已中断", cancelled: "准备已取消", bundle_changed: "原件已变化", commit_conflict: "提交冲突",
};

export function preparationStepText(step: string) {
  return steps[step] ?? "正在准备";
}

export function preparationFailed(preparation: ReadingPreparation | undefined) {
  return !!preparation && Object.hasOwn(failures, preparation.status);
}

export function preparationText(preparation: ReadingPreparation, subject = preparation.candidate ? "新计划" : "阅读") {
  const batch = preparation.step === "document" && preparation.document_batch;
  if (batch) {
    const [first, last] = batch.source_lines;
    const actions = { generate: "正在翻译", retry: `校验重试 ${batch.retry_count}/2`, saved: "已保存", failed: "校验失败" };
    const stopped = preparation.timed_out ? "准备超时" : failures[preparation.status];
    const action = preparation.status === "running" ? actions[batch.action] : stopped;
    const detail = preparation.status === "running" ? batch.message : preparation.error;
    const updated = new Date(batch.last_progress_at).toLocaleTimeString();
    return `${action} · 第 ${batch.index}/${batch.total} 批（原文第 ${first}–${last} 行） · 已保存 ${batch.completed} 批 · 最近进展 ${updated}${detail ? ` · ${detail}` : ""}`;
  }
  if (preparation.timed_out) return "准备超时";
  if (preparation.status === "running") {
    const step = preparationStepText(preparation.step);
    const progress = preparation.total > 0 ? ` · ${preparation.completed}/${preparation.total} 段` : "";
    return `${subject}准备中 · ${step}${progress}`;
  }
  const status = failures[preparation.status] ?? "准备未完成";
  return `${subject}${status}${preparation.error ? ` · ${preparation.error}` : ""}`;
}
