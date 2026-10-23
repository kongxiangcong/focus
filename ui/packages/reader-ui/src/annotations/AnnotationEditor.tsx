import { useLayoutEffect, useRef } from "react";

export function AnnotationEditor({ value, onChange, onSave, onCancel, busy = false, conflict }: {
  value: string; onChange: (value: string) => void; onSave: () => void; onCancel: () => void;
  busy?: boolean; conflict?: string;
}) {
  const input = useRef<HTMLTextAreaElement>(null), composing = useRef(false);
  useLayoutEffect(() => {
    const el = input.current;
    el?.focus({ preventScroll: true }); el?.setSelectionRange(el.value.length, el.value.length);
  }, []);
  useLayoutEffect(() => {
    const el = input.current;
    if (el) { el.style.height = "auto"; el.style.height = `${Math.min(240, Math.max(64, el.scrollHeight))}px`; }
  }, [value]);
  return <div className="reader-anno-editor">
    {conflict && <p role="alert">当前备注：{conflict}。你的草稿已保留，保存将应用到当前版本。</p>}
    <textarea ref={input} aria-label="备注文字" placeholder="写下你的备注…" value={value} maxLength={2000}
      onChange={event => onChange(event.target.value)}
      onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={event => {
        if (event.nativeEvent.isComposing || composing.current || event.keyCode === 229) return;
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onCancel(); }
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault(); if (!busy && value.trim()) onSave();
        }
      }} />
    <div className="reader-anno-editor__bar"><small>Enter 保存 · Shift+Enter 换行 · Esc 取消</small>
      <button type="button" className="reader-anno-ghost" onClick={onCancel}>取消</button>
      <button type="button" className="reader-anno-primary" disabled={busy || !value.trim()} onClick={onSave}>保存</button>
    </div>
  </div>;
}
