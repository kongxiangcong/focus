export function canDismissReaderLayer(event: KeyboardEvent) {
  return event.key === "Escape" && !event.defaultPrevented && !event.isComposing &&
    event.keyCode !== 229 && !document.querySelector("dialog[open]");
}
