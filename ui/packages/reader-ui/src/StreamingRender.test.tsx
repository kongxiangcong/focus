import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const parse = vi.hoisted(() => vi.fn(({children}: {children:string}) => children));
vi.mock("react-markdown", () => ({default: parse, defaultUrlTransform: (url:string) => url}));
import { MarkdownContent } from "./MarkdownContent";
afterEach(cleanup);
it("does not reparse stable history or reading text when streaming changes parent handlers", () => {
  const {rerender} = render(<MarkdownContent text="稳定的正文" figures={[]} onFigure={vi.fn()} />);
  expect(parse).toHaveBeenCalledTimes(1);
  for (let i=0;i<100;i++) rerender(<MarkdownContent text="稳定的正文" figures={[]} onFigure={vi.fn()} />);
  expect(parse).toHaveBeenCalledTimes(1);
  rerender(<MarkdownContent text="更新的正文" figures={[]} onFigure={vi.fn()} />);
  expect(parse).toHaveBeenCalledTimes(2);
});
