export function ingestionFormat(fileName: string): "PDF" | "HTML" | "Markdown" | undefined {
  if (/\.pdf$/i.test(fileName)) return "PDF";
  if (/\.html$/i.test(fileName)) return "HTML";
  if (/\.(md|markdown)$/i.test(fileName)) return "Markdown";
}
