export type Theme = "light" | "dark" | "system";
export type Density = "compact" | "comfortable";
export const accents = ["blue", "green", "red", "neutral"] as const;
export type Accent = typeof accents[number];

export function readPreference<T extends string>(key: string, values: readonly T[], fallback: T, storageFallback = fallback): T {
  try { const value = localStorage.getItem(key); return values.includes(value as T) ? value as T : fallback; }
  catch { return storageFallback; }
}

export const readTheme = (): Theme => readPreference("focus.theme", ["light", "dark", "system"], "system", "light");
export const readAccent = (): Accent => readPreference("focus.accent", accents, "blue");

/** Presentation only: never invokes Host configuration or connectivity. */
export function applyAppearance(theme: Theme, accent: Accent, density: Density, reducedMotion = false) {
  const resolved = theme === "system" ? (globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
  document.documentElement.dataset.reducedMotion = String(reducedMotion);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.accent = accent;
  document.documentElement.dataset.density = density;
}

export function initializeAppearance() {
  applyAppearance(readTheme(), readAccent(),
    readPreference("focus.density", ["compact", "comfortable"], "compact"), readPreference("focus.reducedMotion", ["true", "false"], "false") === "true");
}
