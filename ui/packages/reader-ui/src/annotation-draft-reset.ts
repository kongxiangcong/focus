/** Erase only this Source's recoverable annotation input after an explicit clear receipt. */
export function clearAnnotationDrafts(sourceId: string): void {
  for (const key of ["focus.annotationDrafts", "focus.chunkNoteDrafts"]) {
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(key) ?? "{}");
      if (!stored || typeof stored !== "object" || Array.isArray(stored)) continue;
      const remaining = Object.fromEntries(Object.entries(stored).filter(([owner]) => !owner.startsWith(`${sourceId}:`)));
      sessionStorage.setItem(key, JSON.stringify(remaining));
    } catch { /* Unavailable storage must not block the clear operation. */ }
  }
}
