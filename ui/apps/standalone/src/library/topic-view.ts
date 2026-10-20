import type { StatusFilter } from "./source-status";
// Core Topic IDs allow only letters, numbers and hyphens; this value is presentation-only.
export const UNFILED = "/__focus_unfiled__";
export function sortingDisabledReason({ managementBusy, query, statusFilter = "all", libraryView, canManage }: { managementBusy: boolean; query: string; statusFilter?: StatusFilter; libraryView: "list" | "cards"; canManage: boolean }) {
  return managementBusy ? "当前任务正在使用材料，暂不能调整专题顺序。" : query ? "搜索时暂停排序；清除搜索后可调整专题顺序。" : statusFilter !== "all" ? "筛选时暂停排序；显示全部状态后可调整专题顺序。" : libraryView === "cards" ? "切换到列表视图后可调整专题顺序" : !canManage ? "当前宿主不支持调整专题顺序。" : "";
}
