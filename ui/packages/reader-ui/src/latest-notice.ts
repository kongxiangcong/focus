import { useState } from "react";

/** Presentation-only dismissal. Reflow and repeated navigation cannot reset a frontier. */
export function useLatestNotice(scope: string, progress: string, requested: boolean) {
  const key = JSON.stringify([scope, progress]);
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());
  const [cycle, setCycle] = useState({ scope, key, ready: true });
  // Do not interpret the old viewport during progress advancement as a new review.
  // A different source/session is independent, while a new frontier must settle first.
  if (cycle.key !== key) {
    setCycle({ scope, key, ready: cycle.scope !== scope || !requested });
  } else if (!requested && !cycle.ready) {
    setCycle({ ...cycle, ready: true });
  }
  return {
    visible: cycle.key === key && cycle.ready && requested && !dismissed.has(key),
    dismiss: () => setDismissed(old => new Set(old).add(key)),
  };
}
