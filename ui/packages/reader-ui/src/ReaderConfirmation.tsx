import { useId, useLayoutEffect, useRef } from "react";

export interface ReaderConfirmationInput {
  title: string;
  description: string;
  label: string;
  opener: HTMLElement;
  confirm: () => void;
}

export function ReaderConfirmation({ input, onClose }: { input: ReaderConfirmationInput; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useLayoutEffect(() => {
    const node = dialog.current;
    node?.showModal();
    cancel.current?.focus({ preventScroll: true });
    return () => {
      node?.close();
      if (input.opener.isConnected) input.opener.focus({ preventScroll: true });
    };
  }, [input.opener]);
  return <dialog className="focus-dialog" ref={dialog} aria-labelledby={titleId} aria-describedby={descriptionId}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <h2 id={titleId}>{input.title}</h2>
    <p id={descriptionId}>{input.description}</p>
    <div className="focus-confirm-actions">
      <button type="button" ref={cancel} onClick={onClose}>取消</button>
      <button type="button" onClick={() => { onClose(); input.confirm(); }}>{input.label}</button>
    </div>
  </dialog>;
}
