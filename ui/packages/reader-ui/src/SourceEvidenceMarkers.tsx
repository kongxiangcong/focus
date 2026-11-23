import { createContext, useContext, useLayoutEffect, useRef } from "react";
import type { ReaderMessage, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { hastAnnotatableText } from "./annotatable-text";
import { markdownTree } from "./markdown-pipeline";

export const ActiveSourceCitation = createContext<string | undefined>(undefined);

export function SourceEvidenceMarkers({ items }: { items: readonly ValidatedAnswerEvidence[] }) {
  const activeId = useContext(ActiveSourceCitation);
  if (!items.length) return null;
  const answerCount = new Set(items.map(item => item.messageId)).size;
  const active = items.find(item => item.evidenceId === activeId);
  return <span className="source-evidence-markers" data-anno-ui="">
    {answerCount === 1 ? <button type="button" className="source-evidence-number"
      data-evidence-answer={items[0].messageId} aria-label="返回相关回答">1 条回答</button> : <button type="button" className="source-evidence-number"
      data-evidence-choices={items.map(item => item.evidenceId).join(" ")} aria-haspopup="dialog"
      aria-label={`查看 ${answerCount} 条相关回答`}>{answerCount} 条回答</button>}
    {active && <button type="button" className="source-evidence-number" data-evidence={active.evidenceId} data-origin="true"
      aria-label={`返回回答证据 ${active.displayNumber}`}>{active.displayNumber}</button>}
  </span>;
}

export function SourceAnswerChooser({ items, answers, onChoose, onClose }: {
  items: readonly ValidatedAnswerEvidence[];
  answers: readonly ReaderMessage[];
  onChoose: (messageId: string) => void;
  onClose: () => void;
}) {
  const first = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => { first.current?.focus({ preventScroll: true }); }, []);
  const linked = answers.flatMap((answer, index) => {
    const citation = items.find(item => item.messageId === answer.messageId);
    return citation ? [{ answer, ordinal: index + 1, citation }] : [];
  });
  return <aside className="source-evidence-card source-answer-chooser" role="dialog" aria-label="选择回答">
    <button type="button" aria-label="关闭回答选择" onClick={onClose}>×</button>
    <ul>{linked.map(({ answer, ordinal, citation }, index) => <li key={answer.messageId}>
      <button type="button" ref={index === 0 ? first : undefined} onClick={() => onChoose(answer.messageId)}>
        <span>回答 {ordinal}</span>
        <span>{answerExcerpt(answer, citation.evidenceId)}</span>
      </button>
    </li>)}</ul>
  </aside>;
}

function answerExcerpt(answer: ReaderMessage, evidenceId: string) {
  const marker = `[[e:${evidenceId}]]`;
  const anchor = answer.content.indexOf(marker);
  const before = answer.content.slice(0, anchor).trimEnd().split(/\n\s*\n/).at(-1) ?? "";
  const after = answer.content.slice(anchor + marker.length).split(/\n\s*\n/)[0];
  const text = hastAnnotatableText(markdownTree(`${before}\uFFFC${after}`.replace(/\[\[e:[0-9a-f]{24}\]\]/g, "")))
    .replace(/\s+/g, " ").trim();
  const [head, tail = ""] = text.split("\uFFFC");
  const past = Array.from(head), next = Array.from(tail);
  return `${past.length > 110 ? "…" : ""}${past.slice(-110).join("")}${next.slice(0, 40).join("")}${next.length > 40 ? "…" : ""}`;
}
