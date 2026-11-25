import { createReaderId } from "@focus/reader-contracts";
import { useCallback, useRef, useState } from "react";

type EvidenceNavigationRequest = {
  sourceId: string;
  messageId: string;
  evidenceId: string;
} & (
  | { destination?: "source"; preferredView: "pdf" | "translation" | "source"; keyboard?: boolean }
  | { destination: "answer"; discussionId: string; bundleVersion?: string | null; sourceGeneration?: number }
);

export type EvidenceNavigationIntent = EvidenceNavigationRequest & { nonce: string };

export interface EvidenceNavigation {
  intent: EvidenceNavigationIntent | null;
  start: (input: EvidenceNavigationRequest) => EvidenceNavigationIntent;
  isLatest: (intent: EvidenceNavigationIntent) => boolean;
  consume: (intent: EvidenceNavigationIntent) => boolean;
  cancel: () => void;
}

export function useEvidenceNavigation(): EvidenceNavigation {
  const [intent, setIntent] = useState<EvidenceNavigationIntent | null>(null);
  const pending = useRef<EvidenceNavigationIntent | null>(null);
  const latest = useRef<EvidenceNavigationIntent | null>(null);
  const start = useCallback((input: EvidenceNavigationRequest) => {
    const next = { ...input, nonce: createReaderId() };
    latest.current = next;
    pending.current = next;
    setIntent(next);
    return next;
  }, []);
  const isLatest = useCallback((candidate: EvidenceNavigationIntent) => latest.current?.nonce === candidate.nonce, []);
  const consume = useCallback((candidate: EvidenceNavigationIntent) => {
    if (pending.current?.nonce !== candidate.nonce) return false;
    pending.current = null;
    setIntent(null);
    return true;
  }, []);
  const cancel = useCallback(() => {
    latest.current = null;
    pending.current = null;
    setIntent(null);
  }, []);
  return { intent, start, isLatest, consume, cancel };
}
