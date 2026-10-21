export const readingFontSizes = {
  small: 16,
  standard: 18,
  large: 22,
  extra: 26,
} as const;

export const readingMeasures = [
  { id: "narrow", label: "窄", characters: 36 },
  { id: "standard", label: "标准", characters: 42 },
  { id: "wide", label: "宽", characters: 50 },
  { id: "full", label: "超宽", characters: 62 },
] as const;
export type ReadingMeasure = typeof readingMeasures[number]["id"];
export const readingLayout = { padding: 48, noteGap: 32, noteWidth: 280 } as const;
export const measureWidth = (id: ReadingMeasure, fontSize: number) => readingMeasures.find(m => m.id === id)!.characters * fontSize;
export function readReadingMeasure(storage: Pick<Storage, "getItem" | "setItem" | "removeItem">, fontSize: number): ReadingMeasure {
  const saved = storage.getItem("focus.readingMeasure");
  let measure: ReadingMeasure = readingMeasures.some(m => m.id === saved) ? saved as ReadingMeasure : "standard";
  if (!saved) {
    const legacy = storage.getItem("focus.readingWidth") ?? storage.getItem("focus.standardWidth");
    const width = legacy === "wide" ? Infinity : legacy === "standard" ? Number(storage.getItem("focus.standardWidth") ?? 1040) : Number(legacy);
    if (legacy === "wide") measure = "full";
    else if (legacy !== null && Number.isFinite(width) && width > 0) measure = readingMeasures.reduce((best, candidate) =>
      Math.abs(measureWidth(candidate.id, fontSize) - width) < Math.abs(measureWidth(best.id, fontSize) - width) ? candidate : best).id;
    storage.setItem("focus.readingMeasure", measure);
  }
  storage.removeItem("focus.readingWidth"); storage.removeItem("focus.standardWidth");
  return measure;
}
export function effectiveReadingMeasure(preferred: ReadingMeasure, fontSize: number, available: number, reserve = 0): ReadingMeasure {
  if (!available || measureWidth(preferred, fontSize) + readingLayout.padding + reserve <= available) return preferred;
  return [...readingMeasures].reverse().find(m => measureWidth(m.id, fontSize) + readingLayout.padding + reserve <= available)?.id ?? "narrow";
}
