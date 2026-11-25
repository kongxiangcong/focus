export type Theme = "light" | "dark" | "system";
export const accents = ["blue", "green", "red", "neutral"] as const;
export type Accent = typeof accents[number];

declare global {
  interface Window {
    focusTheme?: {
      preference: Theme;
      accent: Accent;
      systemColorScheme?: MediaQueryList;
      resolve: (theme: Theme) => Exclude<Theme, "system">;
    };
  }
}

export function readPreference<T extends string>(key: string, values: readonly T[], fallback: T): T {
  try { const value = localStorage.getItem(key); return values.includes(value as T) ? value as T : fallback; }
  catch { return fallback; }
}

export const readTheme = (): Theme => window.focusTheme?.preference ?? "light";
export const readAccent = (): Accent => window.focusTheme?.accent ?? "blue";
export const systemColorScheme = () => window.focusTheme?.systemColorScheme;

/** Presentation only: never invokes Host configuration or connectivity. */
export function applyAppearance(theme: Theme, accent: Accent, reducedMotion = false) {
  const settings = window.focusTheme;
  if (settings) { settings.preference = theme; settings.accent = accent; }
  const resolved = settings?.resolve(theme) ?? (theme === "dark" ? "dark" : "light");
  document.documentElement.dataset.reducedMotion = String(reducedMotion);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.accent = accent;
}

export function initializeAppearance() {
  applyAppearance(readTheme(), readAccent(),
    readPreference("focus.reducedMotion", ["true", "false"], "false") === "true");
}
