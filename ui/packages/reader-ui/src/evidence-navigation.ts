import { createReaderId } from "@focus/reader-contracts";
import { useCallback, useRef, useState } from "react";

type EvidenceNavigationRequest = {
  sourceId: string;
  messageId: string;
  evidenceId: string;
  selectionGeneration?: number;
} & (
  | { destination?: "source"; discussionId?: string; preferredView: "pdf" | "translation" | "source"; keyboard?: boolean }
  | { destination: "answer"; discussionId: string; bundleVersion?: string | null; sourceGeneration?: number }
);

export type EvidenceNavigationIntent = EvidenceNavigationRequest & { nonce: string };

export interface EvidenceNavigation {
  intent: EvidenceNavigationIntent | null;
  start: (input: EvidenceNavigationRequest) => EvidenceNavigationIntent;
  isLatest: (intent: EvidenceNavigationIntent) => boolean;
  consume: (intent: EvidenceNavigationIntent) => boolean;
  cancel: () => void;
  beginDiscussionReset: (sourceId: string, discussionId?: string) => () => void;
  isResettingDiscussion: (sourceId: string, discussionId?: string) => boolean;
}

export function useEvidenceNavigation(): EvidenceNavigation {
  const [intent, setIntent] = useState<EvidenceNavigationIntent | null>(null);
  const [resetting, setResetting] = useState<{ sourceId: string; discussionId?: string } | null>(null);
  const pending = useRef<EvidenceNavigationIntent | null>(null);
  const start = useCallback((input: EvidenceNavigationRequest) => {
    const next = { ...input, nonce: createReaderId() };
    pending.current = next;
    setIntent(next);
    return next;
  }, []);
  const isLatest = useCallback((candidate: EvidenceNavigationIntent) => pending.current?.nonce === candidate.nonce, []);
  const consume = useCallback((candidate: EvidenceNavigationIntent) => {
    if (pending.current?.nonce !== candidate.nonce) return false;
    pending.current = null;
    setIntent(null);
    return true;
  }, []);
  const cancel = useCallback(() => {
    pending.current = null;
    setIntent(null);
  }, []);
  const beginDiscussionReset = useCallback((sourceId: string, discussionId?: string) => {
    const scope = { sourceId, discussionId };
    cancel();
    setResetting(scope);
    return () => setResetting(current => current === scope ? null : current);
  }, [cancel]);
  const isResettingDiscussion = useCallback((sourceId: string, discussionId?: string) =>
    resetting?.sourceId === sourceId && resetting.discussionId === discussionId, [resetting]);
  return { intent, start, isLatest, consume, cancel, beginDiscussionReset, isResettingDiscussion };
}
