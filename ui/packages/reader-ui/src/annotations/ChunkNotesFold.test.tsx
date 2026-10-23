import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChunkNotesFold } from "./ChunkNotesFold";
afterEach(cleanup);
it("folds existing paragraph notes with accessible expansion and an inert closed panel", () => {
  render(<ChunkNotesFold count={2} canCreate onCreate={vi.fn()}><p>段落笔记</p></ChunkNotesFold>);
  const toggle = screen.getByRole("button", { name: /小段笔记 · 2/ });
  const panel = document.getElementById(toggle.getAttribute("aria-controls")!)!;
  expect(toggle).toHaveAttribute("aria-expanded", "false"); expect(panel).toHaveAttribute("inert");
  fireEvent.click(toggle); expect(toggle).toHaveAttribute("aria-expanded", "true"); expect(panel).not.toHaveAttribute("inert");
  fireEvent.click(toggle); expect(toggle).toHaveAttribute("aria-expanded", "false");
});
it("has only create at zero, and keeps editing or fresh notes expanded", () => {
  const create = vi.fn();
  const view = render(<ChunkNotesFold count={0} canCreate onCreate={create}><p>内容</p></ChunkNotesFold>);
  expect(screen.queryByRole("button", { name: /小段笔记 ·/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /记小段笔记/ })); expect(create).toHaveBeenCalledOnce();
  view.rerender(<ChunkNotesFold count={1} canCreate onCreate={create} editing><p>内容</p></ChunkNotesFold>);
  expect(screen.getByRole("button", { name: /小段笔记 · 1/ })).toHaveAttribute("aria-expanded", "true");
});
