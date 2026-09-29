// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type BackendSetupResult, type ReaderHostResult, type ReaderHost } from "@focus/reader-contracts";
import { BackendSetupPanel } from "./BackendSetupPanel";

afterEach(cleanup);
const empty = { status: "empty" as const, source: { sourceId: "", title: "", topicId: null }, current: null, history: [], conversation: [] };

it("checks installation and model access before selecting and applying the backend", async () => {
  const backendSetup = vi.fn(async (action: string, input: { backend: string }) => readerSuccess({
    backend: input.backend, runtimePath: "/private/runtime", status: action === "prepare" ? "installed" : "success", message: "OK",
  }));
  const saveBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const refreshBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const host = { backendSetup, saveBackendConfiguration, refreshBackendConfiguration } as unknown as ReaderHost;
  render(<BackendSetupPanel host={host} />);
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  fireEvent.change(screen.getByRole("combobox", { name: "模型" }), { target: { value: "deepseek-flash" } });
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  await waitFor(() => expect(refreshBackendConfiguration).toHaveBeenCalledOnce());
  expect(backendSetup.mock.calls.map(call => call[0])).toEqual(["prepare", "check"]);
  expect(saveBackendConfiguration).toHaveBeenCalledWith(expect.objectContaining({ backend: "deepseek", model: "deepseek-flash" }));
  expect(screen.queryByText(/private\/runtime/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /保存配置|准备|安装路径/ })).not.toBeInTheDocument();
});

it("does not attempt a connection or save if dependency installation fails", async () => {
  const backendSetup = vi.fn(async () => readerSuccess({ backend: "codex", runtimePath: null, status: "failed", message: "安装失败" }));
  const saveBackendConfiguration = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration, refreshBackendConfiguration: vi.fn() } as unknown as ReaderHost} />);
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  await screen.findByRole("alert");
  expect(backendSetup).toHaveBeenCalledOnce();
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("keeps the current selection when the model request fails", async () => {
  const backendSetup = vi.fn(async (action: string) => readerSuccess({
    backend: "deepseek", runtimePath: null, status: action === "prepare" ? "installed" : "failed", message: "凭据无效",
  }));
  const saveBackendConfiguration = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration, refreshBackendConfiguration: vi.fn() } as unknown as ReaderHost} />);
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("凭据无效");
  expect(backendSetup.mock.calls.map(call => call[0])).toEqual(["prepare", "check"]);
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("discards a late preparation after unmounting", async () => {
  let resolve!: (value: ReaderHostResult<BackendSetupResult>) => void;
  const backendSetup = vi.fn(() => new Promise<ReaderHostResult<BackendSetupResult>>(done => { resolve = done; }));
  const saveBackendConfiguration = vi.fn();
  const host = { backendSetup, saveBackendConfiguration, refreshBackendConfiguration: vi.fn() } as unknown as ReaderHost;
  const app = render(<BackendSetupPanel host={host} />);
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  app.unmount();
  await act(async () => resolve(readerSuccess({ backend: "codex", runtimePath: "/codex", status: "installed", message: "OK" })));
  expect(backendSetup).toHaveBeenCalledOnce();
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});
