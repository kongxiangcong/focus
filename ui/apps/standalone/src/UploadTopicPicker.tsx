import { useId, useRef, useState } from "react";
import type { LibraryTopic } from "@focus/reader-contracts";

export function UploadTopicPicker({ topics, value, onChange, disabled }: {
  topics: readonly LibraryTopic[];
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState(false);
  const [active, setActive] = useState(-1);
  const choices = [{ topicId: "", title: "不关联专题", value: "" }, ...topics
    .filter(topic => !filter || topic.title.toLocaleLowerCase().includes(value.trim().toLocaleLowerCase()))
    .map(topic => ({ ...topic, value: topic.title }))];
  function select(next: string) {
    onChange(next); setOpen(false); setActive(-1); input.current?.focus();
  }
  return <div className="upload-topic-picker" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    <label htmlFor={`${listId}-input`}>专题（可选）</label>
    <div className="upload-topic-field">
      <input id={`${listId}-input`} ref={input} role="combobox" aria-label="专题"
        aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        disabled={disabled} maxLength={120} value={value} placeholder="不关联专题；也可选择或输入专题"
        onClick={() => { setFilter(false); setOpen(true); setActive(-1); }}
        onChange={event => { onChange(event.target.value); setFilter(true); setOpen(true); setActive(-1); }}
        onKeyDown={event => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault(); setOpen(true);
            setActive(current => event.key === "ArrowDown" ? (current + 1) % choices.length : (current <= 0 ? choices.length : current) - 1);
          } else if (event.key === "Enter" && open && active >= 0) {
            event.preventDefault(); select(choices[active].value);
          } else if (event.key === "Escape" && open) {
            event.preventDefault(); event.stopPropagation(); setOpen(false); setActive(-1);
          }
        }} />
      <button type="button" className="upload-topic-toggle" aria-label="展开已有专题"
        aria-expanded={open} aria-controls={listId} disabled={disabled}
        onClick={() => { setFilter(false); setOpen(!open); setActive(-1); input.current?.focus(); }}>
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
      </button>
    </div>
    {open && <ul id={listId} className="upload-topic-options" role="listbox" aria-label="已有专题">
      {choices.map((choice, index) => <li key={choice.topicId} role="presentation">
        <button type="button" role="option" id={`${listId}-${index}`} tabIndex={-1}
          aria-selected={value === choice.value} data-active={active === index}
          onMouseDown={event => event.preventDefault()} onClick={() => select(choice.value)}>{choice.title}</button>
      </li>)}
    </ul>}
  </div>;
}
