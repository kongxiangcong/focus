export type EmptyKind = "offline" | "library" | "search" | "filter" | "topic";
const copy: Record<EmptyKind, [string, string, string]> = {
  offline: ["!", "无法连接 FOCUS 后端，列表未能读取。已有数据未受影响。", "重新连接"],
  library: ["▤", "知识库还是空的。把 PDF 或 SingleFile HTML 拖到这里，或点击上传。", "上传材料"],
  search: ["⌕", "没有标题匹配这次搜索。", "清除搜索"],
  filter: ["◌", "当前筛选下没有材料。", "显示全部状态"],
  topic: ["#", "这个专题还没有来源。可从任意来源的「管理来源」中加入专题。", "查看全部材料"],
};
export function LibraryEmpty({ kind, disabled, onAction }: { kind: EmptyKind; disabled: boolean; onAction: () => void }) {
  const [icon, text, action] = copy[kind];
  return <div className="library-empty" data-kind={kind} role={kind === "offline" ? "alert" : "status"}><span aria-hidden="true">{icon}</span><p>{text}</p><button className={kind === "library" ? "workspace-primary" : undefined} disabled={disabled} onClick={onAction}>{action}</button></div>;
}
