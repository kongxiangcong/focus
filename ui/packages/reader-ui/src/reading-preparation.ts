import type { ReadingPreparation } from "@focus/reader-contracts";

const steps: Record<string, string> = {
  context: "正在分析全文", plan: "正在生成计划", translate: "正在翻译", check: "正在检查", repair: "正在修订译文",
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
  if (preparation.timed_out) return "准备超时";
  if (preparation.status === "running") {
    const step = preparationStepText(preparation.step);
    const progress = preparation.total > 0 ? ` · ${preparation.completed}/${preparation.total} 段` : "";
    return `${subject}准备中 · ${step}${progress}`;
  }
  const status = failures[preparation.status] ?? "准备未完成";
  return `${subject}${status}${preparation.error ? ` · ${preparation.error}` : ""}`;
}
