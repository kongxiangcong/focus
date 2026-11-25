import { createContext, useContext } from "react";
import type { ValidatedAnswerEvidence } from "@focus/reader-contracts";

export const ActiveSourceCitation = createContext<{ messageId?: string; evidenceId?: string }>({});

export function SourceEvidenceMarkers({ items }: { items: readonly ValidatedAnswerEvidence[] }) {
  const selected = useContext(ActiveSourceCitation);
  if (!items.length) return null;
  const active = items.find(item => item.evidenceId === selected.evidenceId);
  const messageId = selected.messageId && items.some(item => item.messageId === selected.messageId)
    ? selected.messageId : items.at(-1)!.messageId;
  const citation = active ?? items.find(item => item.messageId === messageId)!;
  return <span className="source-evidence-markers" data-anno-ui="">
    <button type="button" className="source-evidence-number" data-evidence={citation.evidenceId}
      data-origin={active ? "true" : undefined} aria-label={`返回回答证据 ${citation.displayNumber}`}>
      {citation.displayNumber}
    </button>
  </span>;
}
