/** Accessible modal focus scope; restored when the conditional modal unmounts. */
export function dialog(node: HTMLElement, close: () => void) {
  const previous = document.activeElement as HTMLElement | null;
  const controls = () => Array.from(node.querySelectorAll<HTMLElement>(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]',
  ));
  queueMicrotask(() => controls()[0]?.focus());
  function keydown(e: KeyboardEvent) {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
    if (e.key === "Tab") {
      const items = controls();
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    }
  }
  node.addEventListener("keydown", keydown);
  return { destroy() { node.removeEventListener("keydown", keydown); previous?.focus(); } };
}
