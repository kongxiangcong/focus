(() => {
  const systemColorScheme = window.matchMedia?.("(prefers-color-scheme: dark)");
  const resolve = theme => theme === "system" ? (systemColorScheme?.matches ? "dark" : "light") : theme;
  let preference = "light";
  let accent = "blue";
  try {
    const savedTheme = localStorage.getItem("focus.theme");
    const savedAccent = localStorage.getItem("focus.accent");
    preference = savedTheme === "light" || savedTheme === "dark" ? savedTheme : "system";
    if (["blue", "green", "red", "neutral"].includes(savedAccent)) accent = savedAccent;
  } catch { /* Use the light defaults when browser storage is unavailable. */ }
  window.focusTheme = { preference, accent, systemColorScheme, resolve };
  document.documentElement.dataset.theme = resolve(preference);
  document.documentElement.dataset.accent = accent;
})();
