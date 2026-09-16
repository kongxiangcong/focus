import { useState } from "react";
import type { ReaderAgentState, ReaderApproval, ReaderApprovalResponse } from "@focus/reader-contracts";

function Approval({ approval, onAnswer }: { approval: ReaderApproval; onAnswer: (input: ReaderApprovalResponse) => void }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);
  function respond(value: ReaderApprovalResponse) { setSent(true); onAnswer(value); }
  return <section className="focus-agent__approval" aria-label={approval.title}>
    <strong>{approval.title}</strong>
    {approval.detail && <pre>{approval.detail}</pre>}
    {approval.questions.map(q => <label key={q.id}>{q.question}
      {q.options?.map(o => <button type="button" key={o.label} disabled={sent} onClick={() => setAnswers({ ...answers, [q.id]: o.label })}>{o.label} — {o.description}</button>)}
      <input aria-label={q.question} value={answers[q.id] ?? ""} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })} />
    </label>)}
    {approval.kind === "input" ? <button disabled={sent} onClick={() => respond({ approvalId: approval.id,
      answers: Object.fromEntries(approval.questions.map(q => [q.id, { answers: [answers[q.id] ?? ""] }])) })}>提交回答</button> :
      approval.choices.map(choice => <button disabled={sent} key={choice} onClick={() => respond({ approvalId: approval.id, decision: choice })}>
        {choice === "accept" ? "允许本次" : choice === "decline" ? "拒绝" : "取消"}</button>)}
  </section>;
}

export function AgentControls({ agent, onStop, onAnswer }: { agent: ReaderAgentState; onStop: () => void; onAnswer: (input: ReaderApprovalResponse) => void }) {
  const run = agent.run;
  if (!run) return null;
  const active = ["running", "approval", "stopping"].includes(run.status);
  const labels = { running: "正在处理", approval: "等待你的操作", stopping: "正在停止", completed: "任务完成", failed: "任务失败", interrupted: "任务已停止" };
  return <div className="focus-agent" aria-label="后台任务">
    <div role="status">{labels[run.status]} {active && <button onClick={onStop} disabled={run.status === "stopping"}>停止任务</button>}</div>
    {run.error && <p role="alert">{run.error}</p>}
    {run.approvals.map(a => <Approval key={a.id} approval={a} onAnswer={onAnswer} />)}
    {run.activity.length > 0 && <details><summary>执行记录 · {run.activity.length}</summary>
      {run.activity.map(a => <details key={a.id}><summary>{a.title} · {a.status}</summary><pre>{a.detail}</pre></details>)}
    </details>}
  </div>;
}
