import { expect, it, vi } from "vitest";

// Dynamic actual import keeps Node-only test helpers out of the browser package's types.
// Vitest stubs CSS modules (including ?raw) unless global CSS processing is enabled.
const { readFileSync } = await vi.importActual<{ readFileSync(path: string, encoding: "utf8"): string }>("node:fs");
const source = (name: string) => readFileSync(decodeURIComponent(new URL(name, import.meta.url).pathname).replace(/^\/(?=[A-Za-z]:\/)/, ""), "utf8");
const annotationsCss = source("./reader-annotations.css");
const tokenCss = source("./focus-tokens.css");
const readerSource = source("./FocusReader.tsx");

it("keeps annotation colours in the product token table", () => {
  const css = annotationsCss;
  expect(css).not.toMatch(/#[\da-f]{3,8}\b/i);
  for (const declaration of css.matchAll(/([\w-]+)\s*:\s*([^;{}]+)[;}]\s*/g)) {
    const [, property, value] = declaration;
    for (const rgba of value.matchAll(/rgba\(([^)]+)\)/g)) {
      const [r, g, b] = rgba[1].split(",").map(Number);
      expect(property.includes("shadow") || (r === g && g === b && (r === 0 || r === 255)), declaration[0]).toBe(true);
    }
  }
});

it("defines annotation tokens in both reading themes", () => {
  const css = annotationsCss;
  const tokens = tokenCss;
  const themes = [tokens.match(/:root\s*\{([^}]+)\}/)![1], tokens.match(/:root\[data-theme=dark\]\s*\{([^}]+)\}/)![1]];
  const required = ["highlight", "highlight-strong", "line", "pending-line", "bulb-bg", "bulb-bg-hover", "bulb-border", "bulb-ink", "bubble", "on-bubble", "hl-icon", "note-icon", "card-gap", "card-offset", "narrow-rail"];
  const names = new Set([...required.map(name => `--reader-anno-${name}`), ...css.matchAll(/var\((--reader-anno-[\w-]+)/g)].map(value => typeof value === "string" ? value : value[1]));
  for (const name of names) {
    for (const theme of themes) expect(theme, name).toMatch(new RegExp(`${name}\\s*:`));
  }
  expect(themes[0]).toMatch(/--reader-ease-pop\s*:\s*cubic-bezier\(\.34,\s*1\.5,\s*\.64,\s*1\)/);
});

it("renders reader highlights with the supplied 700 font weight", () => {
  expect(annotationsCss).toMatch(/\.reader-anno--hl\s*\{[^}]*font-weight:\s*700\s*;/);
  expect(readerSource).toMatch(/import "\.\/mist-reader\.css";\s*import "\.\/reader-annotations\.css";/);
});

it("disables annotation animations and transitions for either reduced motion preference", () => {
  const css = annotationsCss;
  for (const block of [
    css.slice(css.indexOf(":root[data-reduced-motion=true]"), css.indexOf("@media (prefers-reduced-motion: reduce)")),
    css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)")),
  ]) {
    expect(block).toContain("[class*=reader-anno]");
    expect(block).toContain("[class*=reader-chunk-notes]");
    expect(block).toContain("::before");
    expect(block).toContain("::after");
    expect(block).toMatch(/animation:\s*none\s*!important/);
    expect(block).toMatch(/transition:\s*none\s*!important/);
  }
});
