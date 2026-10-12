export const readingFonts = [
  { id: "default", label: "默认字体", family: "var(--reader-serif)" },
  { id: "source-han-serif", label: "思源宋体", family: '"FOCUS Source Han Serif", var(--reader-serif)' },
  { id: "source-han-sans", label: "思源黑体", family: '"FOCUS Source Han Sans", var(--reader-ui)' },
  { id: "neo-zhisong-screen", label: "新致宋屏幕阅读版", family: '"FOCUS Neo ZhiSong Screen", var(--reader-serif)' },
] as const;

export type ReadingFont = typeof readingFonts[number]["id"];

export function readReadingFont(): ReadingFont {
  try {
    const saved = localStorage.getItem("focus.readingFont");
    return readingFonts.find(font => font.id === saved)?.id ?? "default";
  } catch { return "default"; }
}

export function readingFontFamily(id: ReadingFont): string {
  return readingFonts.find(font => font.id === id)!.family;
}
