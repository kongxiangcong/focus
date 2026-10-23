export function placeFloat(element: HTMLElement, rect: DOMRect, stream: HTMLElement, side: "above" | "below", align: "center" | "start") {
  const width = element.offsetWidth || (align === "center" ? 250 : 320), height = element.offsetHeight || (align === "center" ? 36 : 156);
  const availableAbove = rect.top, availableBelow = innerHeight - rect.bottom;
  const actualSide = side === "above" ? availableAbove < 56 ? "below" : "above" : availableBelow < height + 18 && availableAbove > height + 18 ? "above" : "below";
  const center = rect.left + rect.width / 2;
  const left = Math.max(8, Math.min(innerWidth - width - 8, align === "center" ? center - width / 2 : rect.left - 10));
  const top = actualSide === "above" ? rect.top - height - 10 : rect.bottom + 10;
  const root = stream.getBoundingClientRect();
  element.style.left = `${left - root.left + stream.scrollLeft}px`;
  element.style.top = `${Math.max(8, top) - root.top + stream.scrollTop}px`;
  element.style.setProperty("--arrow-x", `${Math.max(14, Math.min(width - 14, center - left))}px`);
  element.dataset.side = actualSide;
}
