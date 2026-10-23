import { useState } from "react";

// Versioned, structured identity: never reuse old chunk-only preferences.
export function discussionFoldKey(workspace: string, source: string, session: string, discussion: string, event: string) {
  return `focus.discussionFold.v1:${JSON.stringify([workspace, source, session, discussion, event])}`;
}
export function useDiscussionFolds() {
  const [memory, setMemory] = useState<Record<string, boolean>>({});
  const collapsed = (key: string) => {
    if (Object.hasOwn(memory, key)) return memory[key];
    try { return localStorage.getItem(key) === "true"; } catch { return false; }
  };
  const setCollapsed = (key: string, value: boolean) => {
    setMemory(old => ({ ...old, [key]: value }));
    try { if (value) localStorage.setItem(key, "true"); else localStorage.removeItem(key); } catch { /* In-memory preference survives unavailable storage. */ }
  };
  return { collapsed, setCollapsed };
}
