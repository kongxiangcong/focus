export type Theme = "light" | "dark" | "system";
export type Density = "compact" | "comfortable";

export function readPreference<T extends string>(key: string, values: readonly T[], fallback: T): T {
  try { const value = localStorage.getItem(key); return values.includes(value as T) ? value as T : fallback; }
  catch { return fallback; }
}

/** Presentation only: never invokes Host configuration or connectivity. */
export function applyAppearance(theme: Theme, density: Density, reducedMotion = false) {
  const resolved = theme === "system" ? (globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
  document.documentElement.dataset.reducedMotion = String(reducedMotion);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.density = density;
}

export function initializeAppearance() {
  applyAppearance(readPreference("focus.theme", ["light", "dark", "system"], "system"),
    readPreference("focus.density", ["compact", "comfortable"], "compact"), readPreference("focus.reducedMotion", ["true", "false"], "false") === "true");
}
