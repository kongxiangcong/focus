import { useCallback, useRef } from "react";
const storageKey = "focus.annotationDrafts";
export function useAnnotationDrafts() {
  const data = useRef<Record<string, string> | null>(null);
  if (data.current === null) {
    try { const stored = JSON.parse(sessionStorage.getItem(storageKey) ?? "{}");
      data.current = Object.fromEntries(Object.entries(stored).filter(([, value]) => typeof value === "string")) as Record<string, string>;
    } catch { data.current = {}; }
  }
  const read = useCallback((key: string) => data.current?.[key], []);
  const write = useCallback((key: string, value: string | null) => {
    if (value === null) delete data.current![key]; else data.current![key] = value;
    try { sessionStorage.setItem(storageKey, JSON.stringify(data.current)); } catch { /* Keep the in-memory draft. */ }
  }, []);
  const clearSource = useCallback((source: string) => {
    for (const key of Object.keys(data.current!)) if (key.startsWith(source + ":")) delete data.current![key];
    try { sessionStorage.setItem(storageKey, JSON.stringify(data.current)); } catch { /* Keep in-memory recovery. */ }
  }, []);
  return { read, write, clearSource };
}
