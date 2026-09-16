import { useState } from "react";
import type { ReaderAgentState, ReaderApproval, ReaderApprovalResponse } from "@focus/reader-contracts";

function Approval({ approval, onAnswer }: { approval: ReaderApproval; onAnswer: (input: ReaderApprovalResponse) => Promise<boolean> }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(false);
  async function respond(value: ReaderApprovalResponse) {
    setSent(true); setError(false);
    try { if (await onAnswer(value)) return; } catch { /* allow retry */ }
    setSent(false); setError(true);
  }
  return <section className="focus-agent__approval" aria-label={approval.title}>
    <strong>{approval.title}</strong>
    {approval.detail && <details><summary>查看详情</summary><pre>{approval.detail}</pre></details>}
    {approval.questions.map(q => <fieldset key={q.id}><legend>{q.question}</legend>
      {q.options?.map(o => <button type="button" key={o.label} disabled={sent} aria-pressed={answers[q.id] === o.label}
        onClick={() => setAnswers({ ...answers, [q.id]: o.label })}>{o.label} — {o.description}</button>)}
      <input aria-label={q.question} value={answers[q.id] ?? ""} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })} />
    </fieldset>)}
    {approval.kind === "input" ? <button disabled={sent} onClick={() => void respond({ approvalId: approval.id,
      answers: Object.fromEntries(approval.questions.map(q => [q.id, { answers: [answers[q.id] ?? ""] }])) })}>提交回答</button> :
      approval.choices.map(choice => <button disabled={sent} key={choice} onClick={() => void respond({ approvalId: approval.id, decision: choice })}>
        {choice === "accept" ? "允许本次" : choice === "decline" ? "拒绝" : "取消"}</button>)}
    {sent && <span role="status">已提交，等待处理</span>}
    {error && <p role="alert">提交失败，请重试。</p>}
  </section>;
}
export function AgentControls({ agent, onStop, onAnswer }: { agent: ReaderAgentState; onStop: () => void; onAnswer: (input: ReaderApprovalResponse) => Promise<boolean> }) {
  const run = agent.run;
  if (!run) return null;
  const active = ["running", "approval", "stopping"].includes(run.status);
  return <div className="focus-agent" aria-label="后台任务">
    {active && <div role="status">{run.status === "stopping" ? "正在停止" : run.status === "approval" ? "等待你的操作" : "正在回答"}
      <button onClick={onStop} disabled={run.status === "stopping"}>停止</button></div>}
    {run.error && <p role="alert">{run.error}</p>}
    {run.approvals.map(a => <Approval key={a.id} approval={a} onAnswer={onAnswer} />)}
    {run.activity.length > 0 && <details><summary>执行记录</summary>
      {run.activity.map(a => <details key={a.id}><summary>{a.title} · {a.status}</summary><pre>{a.detail}</pre></details>)}
    </details>}
  </div>;
}
