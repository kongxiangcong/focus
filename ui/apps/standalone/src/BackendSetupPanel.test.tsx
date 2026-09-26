// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type BackendSetupResult, type ReaderHostResult, type ReaderHost } from "@focus/reader-contracts";
import { BackendSetupPanel } from "./BackendSetupPanel";

afterEach(cleanup);

it("discards a late success after the selected configuration changes without activating a backend", async () => {
  let resolve!: (value: ReaderHostResult<BackendSetupResult>) => void;
  const backendSetup = vi.fn(() => new Promise<ReaderHostResult<BackendSetupResult>>(done => { resolve = done; }));
  const selectBackend = vi.fn();
  const host = { backendSetup, selectBackend } as unknown as ReaderHost;
  render(<BackendSetupPanel host={host} effective="codex" />);
  fireEvent.click(screen.getByRole("button", { name: "连通性检查" }));
  expect(screen.getByRole("status")).toHaveTextContent("检查中");
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  await act(async () => resolve(readerSuccess({ backend: "codex", runtimePath: "/codex", status: "success", message: "旧配置成功" })));
  expect(screen.getByRole("status")).toHaveTextContent("未检查");
  expect(screen.queryByText("旧配置成功")).not.toBeInTheDocument();
  expect(selectBackend).not.toHaveBeenCalled();
});
