import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AnnotationEditor } from "./AnnotationEditor";

afterEach(cleanup);
it("submits Enter, preserves Shift+Enter and composition, and cancels Escape", () => {
  const save = vi.fn(), cancel = vi.fn();
  render(<AnnotationEditor value="我的备注" onChange={vi.fn()} onSave={save} onCancel={cancel} />);
  const input = screen.getByRole("textbox", { name: "备注文字" });
  expect(input).toHaveFocus();
  fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
  fireEvent.compositionStart(input);
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  fireEvent.compositionEnd(input);
  expect(save).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(save).toHaveBeenCalledOnce();
  fireEvent.keyDown(input, { key: "Escape" });
  expect(cancel).toHaveBeenCalledOnce();
});
it("disables empty or in-flight saves and keeps keyboard composition fallback", () => {
  const save = vi.fn();
  const view = render(<AnnotationEditor value="" onChange={vi.fn()} onSave={save} onCancel={vi.fn()} />);
  expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  view.rerender(<AnnotationEditor value="draft" busy onChange={vi.fn()} onSave={save} onCancel={vi.fn()} />);
  fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
  expect(save).not.toHaveBeenCalled();
});
