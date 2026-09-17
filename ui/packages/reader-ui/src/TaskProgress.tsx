import { useEffect, useState } from "react";
import type { ReaderAgentState } from "@focus/reader-contracts";
import "./task-progress.css";

const terminal = { completed: "已完成", failed: "处理失败", interrupted: "已停止" };
const activityNames: Record<string, string> = { commandExecution: "执行操作", fileChange: "保存文件", dynamicToolCall: "调用工具", mcpToolCall: "调用工具", reasoning: "思考中", webSearch: "检索资料" };
function duration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

export function TaskProgress({ run }: { run: ReaderAgentState["run"] }) {
  const [now, setNow] = useState(Date.now);
  const active = !!run && ["running", "approval", "stopping"].includes(run.status);
  useEffect(() => {
    setNow(Date.now());
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active, run?.runId]);
  if (!run) return null;
  const latest = [...run.activity].reverse().find(a => ["inProgress", "running"].includes(a.status));
  const label = run.status === "approval" ? "等待你的操作" : run.status === "stopping" ? "正在停止" :
    run.status in terminal ? terminal[run.status as keyof typeof terminal] :
    run.progress?.label ?? (latest ? activityNames[latest.title] ?? "处理任务" : "等待助手响应");
  const elapsed = run.progress ? duration((run.progress.finishedAt ?? now) - run.progress.startedAt) : null;
  const quiet = run.status === "running" && run.progress && now - run.progress.updatedAt >= 15000;
  return <div className="task-progress" data-active={active} data-status={run.status}>
    <div className="task-progress__line"><span role="status" aria-live="polite">{label}</span>{elapsed && <span className="task-progress__elapsed" aria-label="已用时间">{elapsed}</span>}</div>
    {active && <progress aria-label="任务进行中" />}
    {quiet && <small>暂未收到新进展 · {duration(now - run.progress!.updatedAt)}</small>}
  </div>;
}
