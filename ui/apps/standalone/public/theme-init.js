(() => {
  const root = document.documentElement;
  let theme = "light";
  let accent = "blue";
  try {
    const preference = localStorage.getItem("focus.theme");
    const savedAccent = localStorage.getItem("focus.accent");
    theme = preference === "light" || preference === "dark" ? preference
      : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    if (["blue", "green", "red", "neutral"].includes(savedAccent)) accent = savedAccent;
  } catch { /* Use the light defaults when browser storage is unavailable. */ }
  root.dataset.theme = theme;
  root.dataset.accent = accent;
})();
